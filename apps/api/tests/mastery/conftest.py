"""The practice fixture (a module with a chapter, its subtopic and another topic) and HTTP
clients, shared with the practice tests."""

from tests.api.conftest import client_as  # noqa: F401 (HTTP clients acting as a user)
from tests.practice.conftest import practice  # noqa: F401 (a module with three topics)
