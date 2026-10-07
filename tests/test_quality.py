from lakehouse.silver.quality import clave_is_valid


def test_clave_is_valid(spark):
    rows = [
        ("5" * 50, True),  # 50 digits
        ("5" * 49, False),  # too short
        ("5" * 51, False),  # too long
        ("5" * 49 + "A", False),  # non-digit
        (None, False),  # missing
    ]
    df = spark.createDataFrame(rows, "clave string, expected boolean")

    result = df.select(clave_is_valid().alias("actual"), "expected").collect()

    assert all(r.actual == r.expected for r in result)
