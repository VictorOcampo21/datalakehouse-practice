"""Intentional data quality errors, injected at controlled rates.

At most one error per file, so the manifest gives exactly one expected outcome per file.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from lakehouse.generator.invoice import Invoice, money

DUPLICATE = "duplicate"
TOTAL_MISMATCH = "total_mismatch"
MISSING_FIELD = "missing_field"
INVALID_CLAVE = "invalid_clave"
FUTURE_DATE = "future_date"
MALFORMED_XML = "malformed_xml"

ERROR_TYPES = (DUPLICATE, TOTAL_MISMATCH, MISSING_FIELD, INVALID_CLAVE, FUTURE_DATE, MALFORMED_XML)

BLANKABLE_FIELDS = (
    "issuer_name",
    "issuer_id",
    "receiver_name",
    "receiver_id",
    "consecutive",
    "issued_at",
)


def pick_error(rng: random.Random, rates: dict[str, float]) -> str | None:
    """Draw at most one error type; rates are independent shares of all files."""
    draw = rng.random()
    cumulative = 0.0
    for error in ERROR_TYPES:
        cumulative += rates.get(error, 0.0)
        if draw < cumulative:
            return error
    return None


def apply_error(rng: random.Random, invoice: Invoice, error: str, end_date: date) -> str:
    """Mutate the invoice for content errors. Returns a short detail for the manifest."""
    if error == TOTAL_MISMATCH:
        delta = money(Decimal(rng.randint(100, 50_000)) / 100) * rng.choice((1, -1))
        invoice.total_override = invoice.total_sale + invoice.total_tax + delta
        return f"TotalComprobante off by {delta}"
    if error == MISSING_FIELD:
        name = rng.choice(BLANKABLE_FIELDS)
        invoice.blank_fields.add(name)
        return f"blank {name}"
    if error == INVALID_CLAVE:
        if rng.random() < 0.5:
            invoice.clave = invoice.clave[: -rng.randint(1, 5)]
        else:
            invoice.clave += "".join(str(rng.randint(0, 9)) for _ in range(rng.randint(1, 5)))
        return f"clave length {len(invoice.clave)}"
    if error == FUTURE_DATE:
        future_day = end_date + timedelta(days=rng.randint(365, 730))
        invoice.issued_at = datetime.combine(future_day, invoice.issued_at.timetz())
        invoice.refresh_clave()
        return f"FechaEmision {future_day.isoformat()}"
    raise ValueError(f"not a content error: {error}")


def corrupt(rng: random.Random, payload: bytes) -> bytes:
    """Truncate the XML so it cannot be parsed."""
    cut = rng.randint(int(len(payload) * 0.3), int(len(payload) * 0.8))
    return payload[:cut]
