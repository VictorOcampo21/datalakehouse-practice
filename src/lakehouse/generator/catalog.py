"""Synthetic master data: issuers (with history for SCD2), receivers and products."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal

from faker import Faker

# Subset of IVA rate codes (CodigoTarifaIVA). To verify against the official v4.4 annex.
IVA_RATES: dict[str, Decimal] = {
    "01": Decimal("0.00"),  # exempt (0 %)
    "02": Decimal("1.00"),
    "03": Decimal("2.00"),
    "04": Decimal("4.00"),
    "08": Decimal("13.00"),  # general rate
}

ID_TYPE_PERSON = "01"  # cedula fisica, 9 digits
ID_TYPE_COMPANY = "02"  # cedula juridica, 10 digits

_COMPANY_SUFFIXES = ("S.A.", "S.R.L.", "Ltda.")
_COMPANY_KINDS = (
    "Distribuidora",
    "Comercializadora",
    "Servicios",
    "Inversiones",
    "Suministros",
    "Tecnologia",
    "Importadora",
)
_LANDMARKS = (
    "de la iglesia",
    "del parque central",
    "de la escuela",
    "del supermercado",
    "de la plaza",
)
_DIRECTIONS = ("norte", "sur", "este", "oeste")


@dataclass(frozen=True)
class Party:
    """Issuer (Emisor) or receiver (Receptor) as it appears on one invoice."""

    id_type: str
    id_number: str
    name: str
    commercial_name: str
    province: str
    canton: str
    district: str
    other_signs: str
    email: str
    activity_code: str


@dataclass(frozen=True)
class Issuer:
    """An issuer and its attribute history. Each version is valid from a date onwards."""

    id_type: str
    id_number: str
    versions: tuple[tuple[date, Party], ...]

    def as_of(self, day: date) -> Party:
        current = self.versions[0][1]
        for valid_from, party in self.versions:
            if valid_from <= day:
                current = party
        return current


@dataclass(frozen=True)
class Product:
    cabys: str  # synthetic 13-digit code, not a real CABYS entry
    description: str
    unit: str
    min_price: Decimal  # CRC
    max_price: Decimal  # CRC
    iva_code: str


PRODUCTS: tuple[Product, ...] = (
    Product(
        "9100000000011", "Papel bond carta (resma)", "Unid", Decimal("2500"), Decimal("4500"), "08"
    ),
    Product(
        "9100000000028", "Toner de impresora", "Unid", Decimal("25000"), Decimal("65000"), "08"
    ),
    Product("9100000000035", "Cafe molido 1 kg", "Unid", Decimal("4500"), Decimal("9000"), "01"),
    Product("9100000000042", "Arroz 5 kg", "Unid", Decimal("4000"), Decimal("7000"), "02"),
    Product("9100000000059", "Frijoles 1 kg", "Unid", Decimal("1200"), Decimal("2500"), "02"),
    Product(
        "9100000000066", "Servicio de limpieza (hora)", "h", Decimal("3500"), Decimal("6000"), "08"
    ),
    Product(
        "9100000000073",
        "Consultoria contable (hora)",
        "h",
        Decimal("15000"),
        Decimal("35000"),
        "08",
    ),
    Product(
        "9100000000080",
        "Servicio de transporte de carga",
        "Sp",
        Decimal("20000"),
        Decimal("90000"),
        "08",
    ),
    Product(
        "9100000000097", "Medicamento generico", "Unid", Decimal("1500"), Decimal("12000"), "03"
    ),
    Product(
        "9100000000103", "Servicio medico privado", "Sp", Decimal("25000"), Decimal("60000"), "03"
    ),
    Product(
        "9100000000110", "Insumo agropecuario", "Unid", Decimal("8000"), Decimal("40000"), "04"
    ),
    Product(
        "9100000000127",
        "Licencia de software (mes)",
        "Unid",
        Decimal("10000"),
        Decimal("80000"),
        "08",
    ),
    Product("9100000000134", "Combustible (litro)", "L", Decimal("700"), Decimal("900"), "01"),
    Product(
        "9100000000141", "Mantenimiento de equipo", "Sp", Decimal("30000"), Decimal("150000"), "08"
    ),
    Product(
        "9100000000158", "Material de construccion", "Unid", Decimal("5000"), Decimal("50000"), "08"
    ),
)


def _digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(n))


def _id_number(rng: random.Random, id_type: str) -> str:
    if id_type == ID_TYPE_COMPANY:
        return "3101" + _digits(rng, 6)
    return str(rng.randint(1, 7)) + _digits(rng, 8)


def _address(rng: random.Random) -> tuple[str, str, str, str]:
    province = str(rng.randint(1, 7))
    canton = f"{rng.randint(1, 20):02d}"
    district = f"{rng.randint(1, 10):02d}"
    other = (
        f"{rng.choice((100, 200, 300, 400))} m {rng.choice(_DIRECTIONS)} {rng.choice(_LANDMARKS)}"
    )
    return province, canton, district, other


def _email(name: str) -> str:
    # example.com is reserved (RFC 2606), so no generated address can belong to a real person.
    local = "".join(ch for ch in name.lower() if ch.isalnum())[:15] or "contacto"
    return f"{local}@example.com"


def _new_party(rng: random.Random, fake: Faker, id_type: str, id_number: str) -> Party:
    if id_type == ID_TYPE_COMPANY:
        base = f"{rng.choice(_COMPANY_KINDS)} {fake.last_name()}"
        name = f"{base} {rng.choice(_COMPANY_SUFFIXES)}"
        commercial = base
    else:
        name = f"{fake.first_name()} {fake.last_name()} {fake.last_name()}"
        commercial = name
    province, canton, district, other = _address(rng)
    return Party(
        id_type=id_type,
        id_number=id_number,
        name=name,
        commercial_name=commercial,
        province=province,
        canton=canton,
        district=district,
        other_signs=other,
        email=_email(commercial),
        activity_code=_digits(rng, 6),
    )


def build_issuers(
    rng: random.Random,
    fake: Faker,
    count: int,
    start: date,
    end: date,
    change_rate: float,
) -> list[Issuer]:
    """Issuers; a share of them change name or address once inside [start, end] (for SCD2)."""
    issuers = []
    span = max((end - start).days, 1)
    for _ in range(count):
        id_type = ID_TYPE_COMPANY if rng.random() < 0.7 else ID_TYPE_PERSON
        id_number = _id_number(rng, id_type)
        first = _new_party(rng, fake, id_type, id_number)
        versions = [(start, first)]
        if rng.random() < change_rate and span > 1:
            changed_on = start + timedelta(days=rng.randint(1, span))
            if rng.random() < 0.5:
                new = _new_party(rng, fake, id_type, id_number)
                second = replace(first, name=new.name, commercial_name=new.commercial_name)
            else:
                province, canton, district, other = _address(rng)
                second = replace(
                    first, province=province, canton=canton, district=district, other_signs=other
                )
            versions.append((changed_on, second))
        issuers.append(Issuer(id_type, id_number, tuple(versions)))
    return issuers


def build_receivers(rng: random.Random, fake: Faker, count: int) -> list[Party]:
    """Receivers: the businesses whose purchases the accountant manages."""
    return [
        _new_party(rng, fake, ID_TYPE_COMPANY, _id_number(rng, ID_TYPE_COMPANY))
        for _ in range(count)
    ]
