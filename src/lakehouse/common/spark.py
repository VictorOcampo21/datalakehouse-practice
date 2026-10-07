"""SparkSession helpers shared by entrypoints and tests."""

from pyspark.sql import SparkSession


def get_local_spark(app_name: str = "lakehouse-local") -> SparkSession:
    """Small local SparkSession for unit tests and exploration (not used on Databricks)."""
    return (
        SparkSession.builder.master("local[2]")
        .appName(app_name)
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.sql.session.timeZone", "America/Costa_Rica")
        .getOrCreate()
    )
