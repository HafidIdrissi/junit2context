"""Optional pytest reproduction; not imported by the project's unittest suite."""

import pytest


@pytest.fixture
def unavailable_service():
    raise RuntimeError("synthetic setup unavailable")


def test_passing():
    assert 2 + 2 == 4


def test_failed_assertion():
    assert 2 + 2 == 5, "synthetic assertion diagnostic"


def test_setup_error(unavailable_service):
    assert unavailable_service == "ready"
