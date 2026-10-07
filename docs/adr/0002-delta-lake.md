# ADR 0002: Use Delta Lake as the table format

- **Status:** Accepted
- **Date:** 2026-10-07

## Context

The pipeline needs idempotent upserts (re-running a load must not create duplicates), SCD Type 2 history in a dimension, and protection against bad writes. Plain Parquet files give none of these guarantees.

## Decision

Store every Bronze, Silver and Gold table as a **Delta Lake** table, the default table format on Databricks.

## Consequences

- **ACID transactions:** a failed write never leaves a table half updated.
- **`MERGE INTO`:** idempotent upserts in Silver and SCD Type 2 in Gold.
- **Schema enforcement:** writes with an unexpected schema fail instead of silently corrupting the table. Schema evolution has to be explicit.
- **Time travel:** earlier versions can be queried for debugging and audits.
- **Maintenance:** `OPTIMIZE` and clustering are available for performance work (Phase 6).
- Unit tests run on local PySpark without Delta. Delta-specific behaviour (`MERGE`, time travel) is verified on Databricks.
