"""Data quality rules for the Silver layer.

Each rule is a pure Column expression so it can be unit-tested locally with PySpark
and reused unchanged on Databricks.
"""

from pyspark.sql import Column
from pyspark.sql import functions as F

CLAVE_LENGTH = 50


def clave_is_valid(col_name: str = "clave") -> Column:
    """True when the invoice key (Clave) is exactly 50 digits."""
    return F.coalesce(F.col(col_name).rlike(rf"^\d{{{CLAVE_LENGTH}}}$"), F.lit(False))
