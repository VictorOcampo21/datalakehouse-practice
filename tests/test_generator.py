import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from lakehouse.generator import errors
from lakehouse.generator.cli import GeneratorConfig, generate, main
from lakehouse.generator.invoice import NAMESPACE

NS = {"fe": NAMESPACE}


def _config(output: Path, **overrides) -> GeneratorConfig:
    base = {"invoices": 300, "days": 10, "start_date": date(2026, 1, 1), "output": output}
    base.update(overrides)
    return GeneratorConfig(**base)


def _files(output: Path) -> dict[str, bytes]:
    landing = output / "landing" / "invoices"
    return {p.relative_to(landing).as_posix(): p.read_bytes() for p in landing.rglob("*.xml")}


def _text(root: ET.Element, path: str) -> str:
    return root.findtext(path, namespaces=NS) or ""


def _by_error(manifest, error_type):
    return [row for row in manifest if row["error_type"] == error_type]


def _parse(output: Path, row) -> ET.Element:
    return ET.fromstring((output / "landing" / "invoices" / row["file"]).read_bytes())


def test_same_seed_is_reproducible(tmp_path):
    generate(_config(tmp_path / "a", seed=7))
    generate(_config(tmp_path / "b", seed=7))
    generate(_config(tmp_path / "c", seed=8))

    assert _files(tmp_path / "a") == _files(tmp_path / "b")
    assert _files(tmp_path / "a") != _files(tmp_path / "c")


def test_writes_one_file_per_invoice_and_manifest(tmp_path):
    manifest = generate(_config(tmp_path))

    assert len(manifest) == 300
    assert len(_files(tmp_path)) == 300
    assert (tmp_path / "_meta" / "manifest.csv").exists()
    assert (tmp_path / "_meta" / "issuers.csv").exists()
    assert all(row["file"].startswith("2026/01/") for row in manifest)


def test_clean_invoices_are_valid_and_balanced(tmp_path):
    manifest = generate(_config(tmp_path, error_rates={}))

    assert all(row["error_type"] == "" for row in manifest)
    for row in manifest:
        root = _parse(tmp_path, row)
        clave = _text(root, "fe:Clave")
        assert len(clave) == 50 and clave.isdigit()
        assert clave == row["clave"]

        total_sale = Decimal(_text(root, "fe:ResumenFactura/fe:TotalVenta"))
        total_tax = Decimal(_text(root, "fe:ResumenFactura/fe:TotalImpuesto"))
        total = Decimal(_text(root, "fe:ResumenFactura/fe:TotalComprobante"))
        lines = root.findall("fe:DetalleServicio/fe:LineaDetalle", NS)
        lines_total = sum(Decimal(_text(ln, "fe:MontoTotalLinea")) for ln in lines)

        assert len(lines) >= 1
        assert total == total_sale + total_tax == lines_total


def test_intentional_errors_are_detectable(tmp_path):
    rates = dict.fromkeys(errors.ERROR_TYPES, 0.1)
    config = _config(tmp_path, invoices=600, error_rates=rates)
    manifest = generate(config)

    for error in errors.ERROR_TYPES:
        assert _by_error(manifest, error), f"no files with {error}"

    for row in _by_error(manifest, errors.MALFORMED_XML):
        with pytest.raises(ET.ParseError):
            _parse(tmp_path, row)

    for row in _by_error(manifest, errors.INVALID_CLAVE):
        assert len(_text(_parse(tmp_path, row), "fe:Clave")) != 50

    for row in _by_error(manifest, errors.TOTAL_MISMATCH):
        summary = _parse(tmp_path, row).find("fe:ResumenFactura", NS)
        expected = Decimal(_text(summary, "fe:TotalVenta")) + Decimal(
            _text(summary, "fe:TotalImpuesto")
        )
        assert Decimal(_text(summary, "fe:TotalComprobante")) != expected

    for row in _by_error(manifest, errors.FUTURE_DATE):
        issued = _text(_parse(tmp_path, row), "fe:FechaEmision")
        assert date.fromisoformat(issued[:10]) > config.end_date

    blank_paths = {
        "issuer_name": "fe:Emisor/fe:Nombre",
        "issuer_id": "fe:Emisor/fe:Identificacion/fe:Numero",
        "receiver_name": "fe:Receptor/fe:Nombre",
        "receiver_id": "fe:Receptor/fe:Identificacion/fe:Numero",
        "consecutive": "fe:NumeroConsecutivo",
        "issued_at": "fe:FechaEmision",
    }
    for row in _by_error(manifest, errors.MISSING_FIELD):
        field = row["error_detail"].removeprefix("blank ")
        assert _text(_parse(tmp_path, row), blank_paths[field]) == ""

    clean_claves = {row["clave"] for row in manifest if row["error_type"] == ""}
    for row in _by_error(manifest, errors.DUPLICATE):
        assert row["clave"] in clean_claves


def test_issuer_changes_are_recorded(tmp_path):
    generate(_config(tmp_path, issuers=10, issuer_change_rate=1.0, error_rates={}))

    rows = (tmp_path / "_meta" / "issuers.csv").read_text(encoding="utf-8").splitlines()[1:]
    ids = [row.split(",")[0] for row in rows]
    assert len(rows) == 20  # every issuer has two versions
    assert len(set(ids)) == 10


def test_rejects_error_rates_above_one(tmp_path):
    with pytest.raises(ValueError):
        generate(_config(tmp_path, error_rates=dict.fromkeys(errors.ERROR_TYPES, 0.2)))


def test_cli_runs(tmp_path, capsys):
    assert main(["--invoices", "20", "--days", "2", "--output", str(tmp_path), "--clean"]) == 0
    assert "Wrote 20 files" in capsys.readouterr().out
