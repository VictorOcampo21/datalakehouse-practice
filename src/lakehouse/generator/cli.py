"""Generate synthetic invoice XML files into a landing folder laid out by arrival date.

Output (default ./data, git-ignored):
    landing/invoices/YYYY/MM/DD/FE-0000001.xml   files to upload to the Databricks volume
    _meta/manifest.csv                           expected outcome per file (ground truth)
    _meta/issuers.csv                            issuer attribute history (for SCD2 checks)
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from faker import Faker

from lakehouse.generator import errors
from lakehouse.generator.catalog import build_issuers, build_receivers
from lakehouse.generator.invoice import build_invoice, to_xml

CR_TZ = timezone(timedelta(hours=-6))
USD_SHARE = 0.15
DEFAULT_ERROR_RATE = 0.01

MANIFEST_FIELDS = ("file", "clave", "issuer_id", "arrival_date", "error_type", "error_detail")


@dataclass
class GeneratorConfig:
    invoices: int = 1_000
    days: int = 30
    start_date: date = date(2026, 1, 1)
    seed: int = 42
    output: Path = Path("data")
    issuers: int = 40
    receivers: int = 5
    issuer_change_rate: float = 0.25
    error_rates: dict[str, float] = field(
        default_factory=lambda: dict.fromkeys(errors.ERROR_TYPES, DEFAULT_ERROR_RATE)
    )

    @property
    def end_date(self) -> date:
        return self.start_date + timedelta(days=self.days - 1)


def _exchange_rates(rng: random.Random, start: date, days: int) -> dict[date, Decimal]:
    """Synthetic daily CRC per USD rate (random walk). Not official BCCR data."""
    rates, rate = {}, 510.0
    for offset in range(days):
        rate = min(max(rate + rng.uniform(-2, 2), 480.0), 540.0)
        rates[start + timedelta(days=offset)] = Decimal(f"{rate:.2f}")
    return rates


def generate(config: GeneratorConfig) -> list[dict[str, str]]:
    if config.invoices < 1 or config.days < 1:
        raise ValueError("invoices and days must be >= 1")
    if sum(config.error_rates.values()) > 1:
        raise ValueError("error rates must add up to at most 1")

    rng = random.Random(config.seed)
    fake = Faker("es_MX")
    fake.seed_instance(config.seed)

    issuers = build_issuers(
        rng, fake, config.issuers, config.start_date, config.end_date, config.issuer_change_rate
    )
    receivers = build_receivers(rng, fake, config.receivers)
    fx = _exchange_rates(rng, config.start_date, config.days)

    arrivals = sorted(
        datetime.combine(
            config.start_date + timedelta(days=rng.randrange(config.days)),
            time(rng.randint(7, 18), rng.randint(0, 59), rng.randint(0, 59)),
            tzinfo=CR_TZ,
        )
        for _ in range(config.invoices)
    )

    landing = config.output / "landing" / "invoices"
    next_number: dict[str, int] = defaultdict(int)
    clean: list[tuple[bytes, str, str]] = []  # (payload, clave, issuer_id) of valid invoices
    manifest: list[dict[str, str]] = []

    for index, issued_at in enumerate(arrivals, start=1):
        day = issued_at.date()
        error = errors.pick_error(rng, config.error_rates)
        detail = ""

        if error == errors.DUPLICATE and clean:
            payload, clave, issuer_id = rng.choice(clean)
            detail = "redelivery of an earlier invoice"
        else:
            if error == errors.DUPLICATE:
                error = None  # nothing to duplicate yet
            issuer = rng.choice(issuers)
            next_number[issuer.id_number] += 1
            currency = "USD" if rng.random() < USD_SHARE else "CRC"
            invoice = build_invoice(
                rng,
                issued_at,
                issuer.as_of(day),
                rng.choice(receivers),
                next_number[issuer.id_number],
                currency,
                fx[day] if currency == "USD" else Decimal("1.00"),
            )
            if error in (None, errors.MALFORMED_XML):
                payload = to_xml(invoice)
                if error == errors.MALFORMED_XML:
                    payload = errors.corrupt(rng, payload)
                    detail = "truncated file"
                else:
                    clean.append((payload, invoice.clave, issuer.id_number))
            else:
                detail = errors.apply_error(rng, invoice, error, config.end_date)
                payload = to_xml(invoice)
            clave, issuer_id = invoice.clave, issuer.id_number

        relative = Path(f"{day:%Y/%m/%d}") / f"FE-{index:07d}.xml"
        target = landing / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        manifest.append(
            {
                "file": relative.as_posix(),
                "clave": clave,
                "issuer_id": issuer_id,
                "arrival_date": day.isoformat(),
                "error_type": error or "",
                "error_detail": detail,
            }
        )

    meta = config.output / "_meta"
    meta.mkdir(parents=True, exist_ok=True)
    with (meta / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(manifest)
    with (meta / "issuers.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(("id_number", "valid_from", "name", "province", "canton", "district"))
        for issuer in issuers:
            for valid_from, p in issuer.versions:
                writer.writerow(
                    (p.id_number, valid_from.isoformat(), p.name, p.province, p.canton, p.district)
                )
    return manifest


def _parse_args(argv: list[str] | None) -> GeneratorConfig:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--invoices", type=int, default=1_000, help="number of files to write")
    parser.add_argument("--days", type=int, default=30, help="days of arrivals")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--issuers", type=int, default=40)
    parser.add_argument("--receivers", type=int, default=5)
    parser.add_argument("--issuer-change-rate", type=float, default=0.25)
    parser.add_argument("--clean", action="store_true", help="disable all intentional errors")
    for error in errors.ERROR_TYPES:
        parser.add_argument(
            f"--{error.replace('_', '-')}-rate",
            type=float,
            default=DEFAULT_ERROR_RATE,
            help=f"share of files with error '{error}' (default {DEFAULT_ERROR_RATE})",
        )
    args = parser.parse_args(argv)
    rates = {e: 0.0 if args.clean else getattr(args, f"{e}_rate") for e in errors.ERROR_TYPES}
    return GeneratorConfig(
        invoices=args.invoices,
        days=args.days,
        start_date=args.start_date,
        seed=args.seed,
        output=args.output,
        issuers=args.issuers,
        receivers=args.receivers,
        issuer_change_rate=args.issuer_change_rate,
        error_rates=rates,
    )


def main(argv: list[str] | None = None) -> int:
    config = _parse_args(argv)
    manifest = generate(config)
    counts = Counter(row["error_type"] or "clean" for row in manifest)
    print(f"Wrote {len(manifest)} files to {config.output / 'landing' / 'invoices'}")
    for name, count in sorted(counts.items()):
        print(f"  {name:<15} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
