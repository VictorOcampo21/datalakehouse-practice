# ADR 0003: Ingest incrementally with Auto Loader

- **Status:** Accepted (availability on Free Edition to be verified)
- **Date:** 2026-10-07

## Context

New invoice files arrive daily in a landing volume (`/landing/invoices/YYYY/MM/DD/`). Re-reading the entire folder on each run gets slower as data grows. It also needs custom bookkeeping to avoid ingesting the same file twice.

## Decision

Use **Auto Loader** (`cloudFiles`) with a checkpoint and `trigger(availableNow=True)`. Each run processes only the files that are new since the last run, then stops.

## Consequences

- Running the job twice does not duplicate data, because the checkpoint tracks the files already processed.
- The same code can later run as a continuous stream by changing the trigger.
- Corrupt files are recorded instead of stopping the pipeline. They are handled downstream (see ADR 0004).
- Auto Loader is Databricks-specific, so ingestion is not unit-tested locally. Parsing and validation logic are kept separate and tested with local PySpark.
- **To verify:** Auto Loader support and quotas on Databricks Free Edition (serverless). See [platform-notes.md](../platform-notes.md).
