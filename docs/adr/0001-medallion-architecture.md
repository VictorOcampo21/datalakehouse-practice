# ADR 0001: Use a medallion architecture

- **Status:** Accepted
- **Date:** 2026-10-07

## Context

Source data is semi-structured XML invoices. Some are duplicated, malformed, or fail business rules. The end users need a clean dimensional model and KPIs. Loading the XML straight into the final model would mix parsing, validation and modelling in one step. It would also make reprocessing hard and leave no way to audit what arrived.

## Decision

Process the data in three layers:

- **Bronze:** raw XML stored as-is, plus ingestion metadata (file path, size, load time). Append-only.
- **Silver:** parsed, typed, deduplicated and validated data at the invoice and invoice-line grain. Invalid rows go to a quarantine table (see ADR 0004).
- **Gold:** business-facing star schema and KPI views.

## Consequences

- Silver and Gold can be rebuilt from Bronze at any time, for example after a bug fix or a new rule, without asking the source to resend files.
- Each layer has one responsibility, so it is easier to test and debug.
- Bronze keeps the original payload for auditing and lineage.
- Cost: more storage and more tables to maintain. That is acceptable at this scale.
