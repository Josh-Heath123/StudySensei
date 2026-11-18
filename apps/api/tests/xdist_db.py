"""One test database per pytest-xdist worker (imported by conftest before settings load)."""

from sqlalchemy.engine import make_url


def worker_database_url(url: str, worker: str | None) -> str:
    """studysensei_test → studysensei_gw0_test for worker "gw0"; unchanged without a worker.

    The name still ends in _test, so the guard in conftest's ``migrated_db`` applies unchanged.
    """
    parsed = make_url(url)
    name = parsed.database or ""
    if not worker or not name.endswith("_test"):
        return url
    return parsed.set(database=f"{name.removesuffix('_test')}_{worker}_test").render_as_string(
        hide_password=False
    )
