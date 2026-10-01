"""Pytest fixtures for the ScopeGuard local logic tests.

The genlayer stub registration and contract loading live in harness.py so there
is a single shared runtime instance (see harness.py for why).
"""

import pytest

from harness import (
    Address,
    DEFAULT_SCOPE,
    ARTIFACT_URL,
    FUNDER,
    gl,
    scope_guard,
)


@pytest.fixture
def module():
    return scope_guard


@pytest.fixture(autouse=True)
def reset_runtime():
    """Reset the shared gl facade between tests."""
    gl.message.sender_address = Address()
    gl.nondet.web.pages = {}
    gl.nondet.responder = (
        lambda p: '{"verdict": "ON_SCOPE", "cites_scope": true, "rationale": "ok"}'
    )
    yield


@pytest.fixture
def deploy():
    """Return a helper that constructs a ScopeGuard as a given sender."""

    def _deploy(scope=DEFAULT_SCOPE, urls=None, sender=FUNDER):
        if urls is None:
            urls = [ARTIFACT_URL]
        gl.message.sender_address = sender
        return scope_guard.ScopeGuard(scope, urls)

    return _deploy
