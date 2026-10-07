import pytest

from lakehouse.common.spark import get_local_spark


@pytest.fixture(scope="session")
def spark():
    session = get_local_spark("lakehouse-tests")
    yield session
    session.stop()
