# Platform notes: Databricks Free Edition

Template for recording what Databricks Free Edition **actually** supports. Every entry stays "To verify" until it is checked in the workspace. Results are never assumed.

**Last checked:** _not yet_

## Compute

| Item | Status | Notes |
|---|---|---|
| Compute type | To verify | Expected: serverless only |
| Databricks Runtime / Spark version | To verify | |
| Python version | To verify | |
| Usage quotas and limits | To verify | |

## Features used by this project

| Feature | Phase | Status | Notes |
|---|---|---|---|
| Unity Catalog (catalog, schemas, volumes) | 0 | To verify | |
| Auto Loader (`cloudFiles`) | 2 | To verify | |
| Native XML reader (`format("xml")`, `from_xml`) | 2–3 | To verify | Fallback: parse in Python |
| `MERGE INTO` on Delta | 3–4 | To verify | |
| Lakeflow Declarative Pipelines | 6 | To verify | |
| Jobs (multi-task, retries) | 6 | To verify | |
| Databricks Asset Bundles | 6 | To verify | |
| Column masks / row filters | 5 | To verify | Fallback: masking view |
| Groups and `GRANT` | 5 | To verify | |
| Secrets | 5 | To verify | |
| Databricks SQL dashboards | 7 | To verify | |
| Query Profile | 6 | To verify | No classic Spark UI expected on serverless |

## Observations

_Record real observations here (date, what was tested, result)._
