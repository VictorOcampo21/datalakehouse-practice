"""Invoice model, amount calculation and XML serialization (subset modeled on Hacienda v4.4)."""

from __future__ import annotations

import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from lakehouse.generator.catalog import IVA_RATES, PRODUCTS, Party, Product

NAMESPACE = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica"
COUNTRY_CODE = "506"
DOC_TYPE_INVOICE = "01"
SITUATION_NORMAL = "1"
IVA_TAX_CODE = "01"
SYSTEM_PROVIDER_ID = "3101000000"  # synthetic
CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def make_consecutive(number: int, branch: int = 1, terminal: int = 1) -> str:
    """NumeroConsecutivo: branch(3) + terminal(5) + document type(2) + number(10) = 20 digits."""
    return f"{branch:03d}{terminal:05d}{DOC_TYPE_INVOICE}{number:010d}"


def make_clave(issued_at: datetime, issuer_id: str, consecutive: str, security_code: str) -> str:
    """Clave: country(3) + ddmmyy(6) + issuer id(12) + consecutive(20) + situation(1) + code(8)."""
    return (
        COUNTRY_CODE
        + issued_at.strftime("%d%m%y")
        + issuer_id.zfill(12)
        + consecutive
        + SITUATION_NORMAL
        + security_code
    )


@dataclass
class InvoiceLine:
    number: int
    product: Product
    quantity: Decimal
    unit_price: Decimal

    @property
    def total(self) -> Decimal:
        return money(self.quantity * self.unit_price)

    @property
    def tax_rate(self) -> Decimal:
        return IVA_RATES[self.product.iva_code]

    @property
    def tax_amount(self) -> Decimal:
        return money(self.total * self.tax_rate / 100)

    @property
    def line_total(self) -> Decimal:
        return self.total + self.tax_amount


@dataclass
class Invoice:
    issued_at: datetime
    issuer: Party
    receiver: Party
    consecutive: str
    security_code: str
    sale_condition: str
    payment_method: str
    currency: str
    exchange_rate: Decimal
    lines: list[InvoiceLine]
    clave: str = ""
    # Overrides used to inject data quality errors. None means "computed from the lines".
    total_override: Decimal | None = None
    blank_fields: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.clave:
            self.refresh_clave()

    def refresh_clave(self) -> None:
        self.clave = make_clave(
            self.issued_at, self.issuer.id_number, self.consecutive, self.security_code
        )

    @property
    def total_taxed(self) -> Decimal:
        return sum((ln.total for ln in self.lines if ln.tax_rate > 0), Decimal("0.00"))

    @property
    def total_exempt(self) -> Decimal:
        return sum((ln.total for ln in self.lines if ln.tax_rate == 0), Decimal("0.00"))

    @property
    def total_sale(self) -> Decimal:
        return self.total_taxed + self.total_exempt

    @property
    def total_tax(self) -> Decimal:
        return sum((ln.tax_amount for ln in self.lines), Decimal("0.00"))

    @property
    def total_invoice(self) -> Decimal:
        if self.total_override is not None:
            return self.total_override
        return self.total_sale + self.total_tax

    def tax_breakdown(self) -> dict[str, Decimal]:
        breakdown: dict[str, Decimal] = {}
        for ln in self.lines:
            code = ln.product.iva_code
            breakdown[code] = breakdown.get(code, Decimal("0.00")) + ln.tax_amount
        return dict(sorted(breakdown.items()))


def build_invoice(
    rng: random.Random,
    issued_at: datetime,
    issuer: Party,
    receiver: Party,
    consecutive_number: int,
    currency: str,
    exchange_rate: Decimal,
    max_lines: int = 6,
) -> Invoice:
    lines = []
    for number in range(1, rng.randint(1, max_lines) + 1):
        product = rng.choice(PRODUCTS)
        crc_price = Decimal(rng.randint(int(product.min_price), int(product.max_price)))
        unit_price = money(crc_price / exchange_rate)
        quantity = Decimal(rng.randint(1, 20))
        lines.append(InvoiceLine(number, product, quantity, unit_price))
    return Invoice(
        issued_at=issued_at,
        issuer=issuer,
        receiver=receiver,
        consecutive=make_consecutive(consecutive_number),
        security_code=f"{rng.randint(0, 99_999_999):08d}",
        sale_condition=rng.choice(("01", "01", "02")),  # 01 cash, 02 credit
        payment_method=rng.choice(("01", "02", "04")),  # cash, card, transfer
        currency=currency,
        exchange_rate=exchange_rate,
        lines=lines,
    )


def _el(parent: ET.Element, tag: str, text: object | None = None) -> ET.Element:
    child = ET.SubElement(parent, tag)
    if text is not None:
        child.text = str(text)
    return child


def _party(parent: ET.Element, tag: str, party: Party, blank: set[str], prefix: str) -> None:
    node = _el(parent, tag)
    _el(node, "Nombre", "" if f"{prefix}_name" in blank else party.name)
    ident = _el(node, "Identificacion")
    _el(ident, "Tipo", party.id_type)
    _el(ident, "Numero", "" if f"{prefix}_id" in blank else party.id_number)
    if prefix == "issuer":
        _el(node, "NombreComercial", party.commercial_name)
        loc = _el(node, "Ubicacion")
        _el(loc, "Provincia", party.province)
        _el(loc, "Canton", party.canton)
        _el(loc, "Distrito", party.district)
        _el(loc, "OtrasSenas", party.other_signs)
    _el(node, "CorreoElectronico", party.email)


def to_xml(invoice: Invoice) -> bytes:
    ET.register_namespace("", NAMESPACE)
    q = f"{{{NAMESPACE}}}"
    root = ET.Element(f"{q}FacturaElectronica")
    blank = invoice.blank_fields

    _el(root, "Clave", invoice.clave)
    _el(root, "ProveedorSistemas", SYSTEM_PROVIDER_ID)
    _el(root, "CodigoActividadEmisor", invoice.issuer.activity_code)
    _el(root, "CodigoActividadReceptor", invoice.receiver.activity_code)
    _el(root, "NumeroConsecutivo", "" if "consecutive" in blank else invoice.consecutive)
    _el(root, "FechaEmision", "" if "issued_at" in blank else invoice.issued_at.isoformat())
    _party(root, "Emisor", invoice.issuer, blank, "issuer")
    _party(root, "Receptor", invoice.receiver, blank, "receiver")
    _el(root, "CondicionVenta", invoice.sale_condition)

    detail = _el(root, "DetalleServicio")
    for ln in invoice.lines:
        node = _el(detail, "LineaDetalle")
        _el(node, "NumeroLinea", ln.number)
        _el(node, "CodigoCABYS", ln.product.cabys)
        _el(node, "Cantidad", ln.quantity)
        _el(node, "UnidadMedida", ln.product.unit)
        _el(node, "Detalle", ln.product.description)
        _el(node, "PrecioUnitario", ln.unit_price)
        _el(node, "MontoTotal", ln.total)
        _el(node, "SubTotal", ln.total)
        _el(node, "BaseImponible", ln.total)
        tax = _el(node, "Impuesto")
        _el(tax, "Codigo", IVA_TAX_CODE)
        _el(tax, "CodigoTarifaIVA", ln.product.iva_code)
        _el(tax, "Tarifa", ln.tax_rate)
        _el(tax, "Monto", ln.tax_amount)
        _el(node, "ImpuestoNeto", ln.tax_amount)
        _el(node, "MontoTotalLinea", ln.line_total)

    summary = _el(root, "ResumenFactura")
    currency = _el(summary, "CodigoTipoMoneda")
    _el(currency, "CodigoMoneda", invoice.currency)
    _el(currency, "TipoCambio", invoice.exchange_rate)
    _el(summary, "TotalGravado", invoice.total_taxed)
    _el(summary, "TotalExento", invoice.total_exempt)
    _el(summary, "TotalVenta", invoice.total_sale)
    _el(summary, "TotalDescuentos", Decimal("0.00"))
    _el(summary, "TotalVentaNeta", invoice.total_sale)
    for code, amount in invoice.tax_breakdown().items():
        node = _el(summary, "TotalDesgloseImpuesto")
        _el(node, "Codigo", IVA_TAX_CODE)
        _el(node, "CodigoTarifaIVA", code)
        _el(node, "TotalMontoImpuesto", amount)
    _el(summary, "TotalImpuesto", invoice.total_tax)
    payment = _el(summary, "MedioPago")
    _el(payment, "TipoMedioPago", invoice.payment_method)
    _el(payment, "TotalMedioPago", invoice.total_invoice)
    _el(summary, "TotalComprobante", invoice.total_invoice)

    # Hacienda's XML uses a default namespace; children are written unqualified under it.
    for node in root.iter():
        if not node.tag.startswith(q):
            node.tag = q + node.tag
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
