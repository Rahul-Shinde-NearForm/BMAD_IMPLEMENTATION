import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def allow_django_async_unsafe_for_e2e():
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
