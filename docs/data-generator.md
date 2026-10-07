# Synthetic data generator

The pipeline never uses real invoices. Real ones contain taxpayer IDs, names and amounts of third parties. Instead, `lakehouse.generator` writes synthetic XML invoices with a controlled rate of intentional errors, plus a manifest that records the expected outcome for every file.

## Usage

```bash
# 1,000 files over 30 days, ~1 % of each error type (defaults)
generate-invoices

# Larger run, reproducible with a seed
generate-invoices --invoices 100000 --days 365 --start-date 2026-01-01 --seed 42

# No intentional errors
generate-invoices --clean

# Custom error rates (shares of all files)
generate-invoices --total-mismatch-rate 0.05 --malformed-xml-rate 0.02
```

`python -m lakehouse.generator` is equivalent. Run `generate-invoices --help` to see every option.

The same seed and arguments always produce byte-identical files.

## Output

```
data/                                   # git-ignored
├── landing/invoices/YYYY/MM/DD/FE-0000001.xml   # upload this tree to the landing volume
└── _meta/
    ├── manifest.csv    # file, clave, issuer_id, arrival_date, error_type, error_detail
    └── issuers.csv     # issuer attribute history (valid_from), ground truth for SCD2
```

`_meta/` sits outside `landing/`, so Auto Loader never ingests it. The manifest is the ground truth used to check that the Silver layer quarantines exactly the files it should.

## XML structure

The files follow a **simplified subset** of Hacienda's electronic invoice (`FacturaElectronica`) **v4.4**, which has been mandatory since 1 September 2025:

- Root `FacturaElectronica` in the namespace `https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica`.
- Header: `Clave`, `ProveedorSistemas`, `CodigoActividadEmisor`, `CodigoActividadReceptor`, `NumeroConsecutivo`, `FechaEmision`, `Emisor`, `Receptor`, `CondicionVenta`.
- `DetalleServicio/LineaDetalle` (1–6 lines): `CodigoCABYS`, `Cantidad`, `PrecioUnitario`, `MontoTotal`, `SubTotal`, `BaseImponible`, `Impuesto` (`Codigo`, `CodigoTarifaIVA`, `Tarifa`, `Monto`), `MontoTotalLinea`.
- `ResumenFactura`: `CodigoTipoMoneda` (`CodigoMoneda`, `TipoCambio`), `TotalGravado`, `TotalExento`, `TotalVenta`, `TotalDesgloseImpuesto`, `TotalImpuesto`, `MedioPago`, `TotalComprobante`.

**Clave (50 digits):** country `506` (3) + issue date `ddmmyy` (6) + issuer ID zero-padded (12) + `NumeroConsecutivo` (20) + situation (1) + security code (8).

**NumeroConsecutivo (20 digits):** branch (3) + terminal (5) + document type `01` (2) + sequence number per issuer (10).

### Known simplifications (intentional)

- Files are **not signed** and are **not validated against the official XSD**. Only the fields the pipeline uses are included.
- Amounts use 2 decimals, without discounts or exemptions.
- IVA rate codes are a subset (`01` 0 %, `02` 1 %, `03` 2 %, `04` 4 %, `08` 13 %). They are still to be verified against the official v4.4 annex.
- CABYS codes are **synthetic** 13-digit codes, not real catalog entries.
- The USD exchange rate is a synthetic random walk (480–540 CRC). It is not official BCCR data.
- Names come from Faker (`es_MX`; Faker has no `es_CR` locale). IDs are random numbers in the Costa Rican format. Emails use the reserved domain `example.com`.

## Intentional errors

At most one error per file, so each file has a single expected outcome.

| `error_type` | What happens | Silver rule that should catch it |
|---|---|---|
| `duplicate` | An earlier valid invoice is delivered again in a new file (same `Clave`) | Deduplication by `Clave` |
| `total_mismatch` | `TotalComprobante` is off by 1.00–500.00 | `TotalComprobante = TotalVenta + TotalImpuesto` and sum of lines |
| `missing_field` | One required field is empty (issuer or receiver name or ID, `NumeroConsecutivo` or `FechaEmision`) | Required fields present |
| `invalid_clave` | `Clave` is 1–5 digits too short or too long | `Clave` has 50 digits |
| `future_date` | `FechaEmision` is 1–2 years after the generated date range | Issue date not in the future |
| `malformed_xml` | The file is truncated | Parse failure → quarantine (pipeline keeps running) |

## Issuer history (SCD Type 2)

By default, 25 % of issuers (`--issuer-change-rate`) change their **name or address once** inside the date range. From that date on, their invoices carry the new attributes, which feeds the SCD Type 2 `dim_issuer` in Gold. `_meta/issuers.csv` records every version with its `valid_from` date.

## Uploading to Databricks (to verify)

Upload the `landing/invoices` tree to a Unity Catalog volume, keeping the `YYYY/MM/DD` folders. Two options, both **to verify** on Free Edition (see [platform-notes.md](platform-notes.md)):

- The Catalog Explorer UI: "Upload to volume".
- The Databricks CLI: `databricks fs cp -r data/landing/invoices dbfs:/Volumes/<catalog>/<schema>/<volume>/invoices`

Check the Free Edition storage and compute quotas before uploading large volumes.
