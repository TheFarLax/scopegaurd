"""
On-network integration tests for ScopeGuard (real GenLayer consensus).

Unlike tests/test_scope_guard_logic.py (which mocks web + LLM against a stub),
these deploy the contract to an actual GenLayer network (localnet or the
Bradbury testnet) and drive it through the genlayer-test (`gltest`) framework,
so REAL validators fetch the artifact and REAL LLM consensus produces the
verdict.

Requirements to run:
  - Python 3.12+ (gltest/genlayer_py import `collections.abc.Buffer`)
  - `pip install genlayer-test`
  - A reachable network configured in gltest.config.yaml, plus a funded,
    unlocked account (see .env.example / deploy/deploy.py)

Run:  python3 -m pytest tests/test_scope_guard_gltest.py -v

If gltest is not importable (e.g. Python < 3.12) the whole module is skipped so
the local logic suite still runs cleanly.
"""

import pytest

# Skip the entire module unless the on-network toolchain imports cleanly.
# (importorskip only handles ModuleNotFoundError; here an old Python raises a
# bare ImportError from deep inside genlayer_py, so guard it explicitly.)
try:
    from gltest import get_contract_factory
    from gltest.assertions import tx_execution_succeeded
except Exception as _e:  # pragma: no cover - environment dependent
    pytest.skip(
        f"genlayer-test not importable here ({_e}); "
        "run on Python 3.12+ with a configured network.",
        allow_module_level=True,
    )


SCOPE = (
    "Build an on-chain voting module: Solidity/Python smart contracts for "
    "token-weighted proposals, plus documentation and tests."
)

# Two public artifacts the validators actually fetch. Replace with URLs you
# control for a live demo (an on-scope page and an off-scope/pivoted page).
ON_SCOPE_URL = "https://raw.githubusercontent.com/genlayerlabs/genlayer-project-boilerplate/main/README.md"
OFF_SCOPE_URL = "https://raw.githubusercontent.com/torvalds/linux/master/README"

ALLOWED = [ON_SCOPE_URL, OFF_SCOPE_URL]


@pytest.fixture
def factory():
    return get_contract_factory("ScopeGuard")


def _deploy(factory):
    return factory.deploy(args=[SCOPE, ALLOWED])


def test_deploy_and_initial_state(factory):
    contract = _deploy(factory)
    assert contract.get_state(args=[]) == "MONITORING"
    assert contract.get_scope(args=[]) == SCOPE
    assert contract.get_assessment_count(args=[]) == 0


def test_assess_records_a_verdict(factory):
    contract = _deploy(factory)
    receipt = contract.assess(args=[ON_SCOPE_URL])
    assert tx_execution_succeeded(receipt)

    last = contract.get_last_assessment(args=[])
    assert last["verdict"] in (
        "ON_SCOPE",
        "MINOR_DRIFT",
        "MAJOR_DRIFT",
        "UNKNOWN",
    )
    assert contract.get_assessment_count(args=[]) == 1


def test_assess_rejects_non_allowlisted_url(factory):
    contract = _deploy(factory)
    with pytest.raises(Exception):
        contract.assess(args=["https://not-allow-listed.example/x"])


def test_resolve_review_is_funder_only(factory):
    # This only exercises the deterministic guard: resolving from MONITORING
    # must fail regardless of caller.
    contract = _deploy(factory)
    with pytest.raises(Exception):
        contract.resolve_review(args=["RELEASE"])
