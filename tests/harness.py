"""Shared test harness: registers the genlayer stub and loads the contract ONCE.

Both conftest.py (fixtures) and the test modules import from here. Keeping this
in a normal importable module — rather than in conftest.py — avoids the classic
pytest double-import problem (conftest.py gets loaded both as a plugin and via
`from conftest import ...`, which would register two separate `genlayer` stubs
and two `ScopeGuard` classes that don't share runtime state).
"""

import importlib.util
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).parent
ROOT = TESTS_DIR.parent

# Register the stub as the `genlayer` module BEFORE importing the contract.
_spec_stub = importlib.util.spec_from_file_location(
    "genlayer", TESTS_DIR / "genlayer_stub.py"
)
genlayer = importlib.util.module_from_spec(_spec_stub)
sys.modules["genlayer"] = genlayer
_spec_stub.loader.exec_module(genlayer)

# Now load the contract module (its `from genlayer import *` resolves to the stub).
_spec_c = importlib.util.spec_from_file_location(
    "scope_guard", ROOT / "contracts" / "scope_guard.py"
)
scope_guard = importlib.util.module_from_spec(_spec_c)
_spec_c.loader.exec_module(scope_guard)

Address = genlayer.Address
gl = genlayer.gl


FUNDER = Address("0x1111111111111111111111111111111111111111")
STRANGER = Address("0x2222222222222222222222222222222222222222")

DEFAULT_SCOPE = (
    "Build an on-chain voting module: Solidity/Python smart contracts for "
    "token-weighted proposals, plus documentation and tests."
)
ARTIFACT_URL = "https://example.org/deliverable"


def set_llm_verdict(verdict, cites=True, rationale="because"):
    """Make the mocked LLM return a fixed verdict JSON for every prompt."""
    import json as _json

    payload = _json.dumps(
        {"verdict": verdict, "cites_scope": cites, "rationale": rationale}
    )
    gl.nondet.responder = lambda p: payload


def set_page(url, text):
    gl.nondet.web.pages[url] = text
