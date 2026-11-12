import os

# Point every test at the test database before app settings are first read.
# CI sets DATABASE_URL itself; locally this defaults to the docker-compose db.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://studysensei:studysensei@localhost:5433/studysensei_test",
)
