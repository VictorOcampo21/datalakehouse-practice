# ADR 0004: Quarantine invalid records instead of dropping them

- **Status:** Accepted
- **Date:** 2026-10-07

## Context

Some invoices fail validation: the key is not 50 digits, totals do not match the sum of the lines, required fields are missing, the issue date is in the future, or the invoice is a duplicate. Dropping these rows silently hides data problems from the business. Failing the whole pipeline blocks every valid invoice because of a few bad ones.

## Decision

Evaluate named data quality rules in the Silver layer. Rows that pass go to `silver.invoices` and `silver.invoice_lines`. Rows that fail go to `silver.invoices_quarantine` with a `dq_rule_failed` column that names the failed rule. Each run also records quality metrics (rows processed, valid, and quarantined per rule).

## Consequences

- No data is lost. Quarantined rows can be fixed and reprocessed.
- Error rates become a business KPI ("what percentage of invoices arrived with errors, and why?").
- Each rule is a pure function and is unit-tested locally.
- Cost: one more table, and the quarantine needs monitoring so it does not grow unnoticed.
