# ScopeGuard — Scope-Drift Monitor for Grants & Bounties

A GenLayer Intelligent Contract that lets a funder **freeze a scope of work**
on-chain, then lets **anyone** ask the network to judge whether a published
deliverable has drifted from that scope. Every validator independently fetches
the artifact, applies the same natural-language rubric with an LLM, and the
network reaches **consensus on a single drift verdict** that is recorded on
chain as an appealable fact.

```
ON_SCOPE | MINOR_DRIFT | MAJOR_DRIFT | UNKNOWN
```

A `MAJOR_DRIFT` verdict moves the grant into a **REVIEW** state (funds held for a
human decision) — it never seizes anything automatically. The funder then
`RELEASE`s or `CANCEL`s.

## Architecture

```
            deploy(scope_text, allowed_urls)
                      │  funder becomes immutable
                      ▼
        ┌──────────────────────────────┐
        │ ScopeGuard   MONITORING      │   scope frozen at deploy,
        └──────────────┬───────────────┘   no setter ever
                       │ assess(url)  — permissionless
                       ▼
        ┌─────────────────────────────────────────────┐
        │  non-deterministic block (leader + validators)│
        │  1. fetch artifact url         ─ web.render   │
        │  2. rubric prompt: scope vs    ─ exec_prompt  │
        │     artifact (untrusted data)                 │
        │  3. normalize → one of 4 verdicts             │
        └──────────────┬────────────────────────────────┘
                       │ eq_principle: same decision group?
                       ▼            no → tx not ratified
                 consensus (AGREE)
                       │ deterministic post-consensus code
                       ▼
        append Assessment(seq, verdict, …) to history
                       │
        MAJOR_DRIFT? ──┼── no  → stay MONITORING
                       │
                      yes
                       ▼
                     REVIEW  ── funder-only resolve_review
                    /      \
             "RELEASE"   "CANCEL"
                 ▼           ▼
            RELEASED     CANCELLED
```

## Why this needs GenLayer

The core operation is a *subjective, natural-language judgment over live web
content* that must be trustworthy enough to hold funds. A normal smart contract
can't read a web page or reason about "did this deliverable match the promise."
A single off-chain oracle could, but you'd have to trust it. GenLayer is exactly
the fit: many validators each do the fetch + LLM judgment, and the **equivalence
principle** forces them to agree on the verdict group before it becomes an
on-chain fact. That's the whole contract — no cosmetic AI.

## How it works

1. **Deploy** with a frozen `scope_text` and an **allow-list** of artifact URLs.
   The deployer becomes the immutable `funder`. There is deliberately no setter
   for the scope.
2. **`assess(artifact_url)`** (permissionless): inside a non-deterministic block
   each validator fetches the URL, builds a rubric prompt (scope + artifact,
   with the artifact treated as untrusted data), calls the LLM, and normalizes
   the answer to one of the four verdicts. `gl.eq_principle.prompt_comparative`
   requires validators' verdicts to fall in the **same decision group**:
   `{ON_SCOPE, MINOR_DRIFT}` (both keep `MONITORING`), `{MAJOR_DRIFT}` or
   `{UNKNOWN}`. `cites_scope` and rationale wording are ignored. The leader's
   exact verdict is what gets stored.
3. After consensus, deterministic code appends the `Assessment` to history and,
   only on `MAJOR_DRIFT`, transitions `MONITORING → REVIEW`.
4. **`resolve_review(decision)`** (funder-only, REVIEW-only): `RELEASE` →
   `RELEASED`, `CANCEL` → `CANCELLED`.

### Safety properties baked in

- **Prompt-injection resistant**: artifact text is length-bounded
  (`MAX_ARTIFACT_CHARS`) and explicitly framed as untrusted; verdicts are a
  closed enum, so injected text can't invent a verdict. Malformed LLM output
  can at worst revert the transaction — it can never force a state change.
- **Non-determinism is isolated**: the nondet closure never reads or writes
  storage; all storage writes happen after consensus.
- **Allow-list**: only pre-approved URLs can be assessed.
- **Least authority**: assessment is permissionless (anyone can raise a flag),
  but only the funder can resolve the held review.

## GenLayer features used

- `gl.Contract` with annotated storage (`Address`, `str`, `u256`,
  `DynArray[str]`, `DynArray[Assessment]`) and a nested `@allow_storage
  @dataclass` struct.
- `gl.message.sender_address` for the funder identity.
- `gl.nondet.web.render(url, mode="text")` — validator web fetch.
- `gl.nondet.exec_prompt(...)` — validator LLM call.
- `gl.eq_principle.prompt_comparative(fn, principle=...)` — consensus on the
  verdict group.
- `@gl.public.write` / `@gl.public.view`.

## Layout

```
contracts/scope_guard.py           the contract (deploy this)
tests/test_scope_guard_logic.py    local logic tests (stub, plain pytest)
tests/test_scope_guard_gltest.py   on-network integration tests (gltest)
tests/genlayer_stub.py             minimal fake runtime for local testing
tests/harness.py, conftest.py      test wiring/fixtures
deploy/deploy.sh                   CLI deploy wrapper
gltest.config.yaml                 network config for the gltest suite
.env.example                       configuration template
```

## Testing

### Local logic tests (no network, no Docker, Python 3.10+)

```bash
cd tests
python3 -m pytest -q         # 22 passed, 1 skipped
```

**What the 22 passing tests cover** (against a lightweight `genlayer` stub that
mocks web fetches and LLM responses):

| Area | Tests |
|---|---|
| Initial state & views | deploy defaults: `MONITORING`, frozen scope, funder, allow-list, empty history |
| Verdict → state machine | all four verdicts drive the right state (`MINOR_DRIFT`/`UNKNOWN` stay `MONITORING`, only `MAJOR_DRIFT` → `REVIEW`) |
| Equivalence principle | the consensus principle groups `{ON_SCOPE, MINOR_DRIFT}` and keeps `MAJOR_DRIFT`/`UNKNOWN` separate; stored verdict stays exact |
| Permissionless assess | a non-funder can trigger an assessment and is recorded as assessor |
| History accumulation | `seq` increments, verdicts append in order |
| **Allow-list rejection** | a non-allow-listed URL reverts with no state change and nothing recorded |
| **Invalid verdict handling** | an unknown verdict label normalizes to `UNKNOWN`; casing/whitespace are normalized; LLM code fences are stripped |
| **Prompt injection** | non-JSON LLM output (a coerced model) reverts the tx with zero state change; the prompt provably contains the scope, the artifact and an injection guard |
| **Artifact length bounding** | a 50k-char artifact is truncated to `MAX_ARTIFACT_CHARS` in the prompt |
| Unreadable page | a failed fetch reverts, nothing recorded |
| **Unauthorized review resolution** | only the funder can `resolve_review`; bad decisions, wrong state and terminal-state assess are all rejected |
| Terminal states | no further assessments after `RELEASED`/`CANCELLED` |

**Why 1 test is skipped:** the on-network suite
(`tests/test_scope_guard_gltest.py`, real validator consensus via
`genlayer-test`) is auto-skipped in this environment because it requires
Python 3.12+ and the `gltest` toolchain, which this machine's Python 3.10
cannot import (`collections.abc.Buffer`). It is designed to run on a 3.12+
interpreter with a configured network (see `gltest.config.yaml`).

**Live network verification was performed separately** via the `genlayer` CLI
against Bradbury: deploys, consensus receipts, per-validator vote inspection
through the explorer API, and on-chain state reads. Those results are in the
"Live on Bradbury" section below — they are deployment observations, not part
of the pytest run.

### On-network integration tests (Python 3.12+, real consensus)

```bash
pip install genlayer-test          # needs Python 3.12+
# configure gltest.config.yaml + ACCOUNT_PRIVATE_KEY (see .env.example)
python3 -m pytest tests/test_scope_guard_gltest.py -v
```

## Deployment

```bash
cp .env.example .env        # set GENLAYER_ACCOUNT / GENLAYER_RPC
./deploy/deploy.sh          # runs: genlayer deploy --contract contracts/scope_guard.py ...
```

The contract targets the **Bradbury testnet** and pins the stdlib via the
`# { "Depends": "py-genlayer:..." }` pragma on line 1.

The pragma line must be followed by a **blank line**. If a `#` comment sits
directly below it, GenVM rejects the contract with
`invalid_contract: trailing characters at line 1 column 84`.

### Live on Bradbury

Deployer / funder: `scopeguard`, `0xb1E76fdeED6b54D66C47fFf79d63F45331757286`.

| Instance | Address | Deploy tx |
|---|---|---|
| A (README.adoc + Linux README allow-list, exact-match principle) | `0x72e537A819824C5c706A8297B16C3F2A845C876F` | `0xa55fb68587c0b7411854269a36a069416790b1ef1c4fc0763b009029c4eac074` |
| B (GovernorVotes.sol + Linux README allow-list, exact-match principle) | `0x0CC76B7f64a33Eaed4736e1154F08be0B47c6d81` | `0xa499694676f8c824043ae6d0dc6846c686f567a8d06d5cf9c524021ba6ee45ad` |
| C (B's allow-list, grouped-verdict principle — current code) | `0xfE7f11193a828cd79Fd46309e0a496064B500287` | `0xe6ec03007fbbb21e30bb5880da299687493050feecdfec4f300cc41e741b32d9` |

All three deploys were ACCEPTED with AGREE and FINISHED_WITH_RETURN. A and B
run the earlier exact-verdict principle; B differs from A only in its
constructor allow-list (`ALLOWED_URLS=... ./deploy/deploy.sh`). C runs the
current source: same allow-list as B, with the grouped-verdict principle.

**Off-scope flow (instance A)** — the drift path end-to-end:

| Step | Tx | Consensus | Result |
|---|---|---|---|
| `assess(linux README)` | `0x7d1dae6ecd62709f42d2adbb27aa756cb4984b181c4343f3343975e8051f3a61` | AGREE (4 agree, 1 timeout) | `MAJOR_DRIFT`, state `REVIEW` |
| `resolve_review("CANCEL")` from non-funder `0x42dB…1E79` | `0xfd995fb4cb6a4ec0d4d778dbeffdfc99dc5b4d25ccb11ddad760f7ec2bee5d04` | AGREE, FINISHED_WITH_ERROR | reverted: "only the funder can resolve a review", state still `REVIEW` |
| `resolve_review("CANCEL")` from funder | `0xd4820bad2cbdf5d4a1e0c181955b285cafdcd815fa9f97de4167a716bf737819` | AGREE (5/5) | state `CANCELLED` |

**On-scope ratification, observed before and after the principle change.**
Under the earlier exact-verdict principle, five on-scope attempts were made
across A and B, and none was ratified — the leader proposed `ON_SCOPE` each
time, but validators timed out or returned `nondet_disagree`, so no state
change ever committed:

| # | Instance | Tx | Outcome |
|---|---|---|---|
| 1 | A | `0x9fa19d07f572b1b694e09c8f02404eb30e8a3fddc5726686c3a9cf6b4eea9d8d` | majority_timeout (2 agree, 3 timeout) |
| 2 | A | `0xe3b3ea8818a24368365f96c91bf0495bdc6368aea147495f52c0c8d20162f84c` | leader error — 3 validators `finished_with_error`, 2 `nondet_disagree` |
| 3 | A | `0xdfd7e2da6d489aab63c8b6f8ee41e191a5aa22b28b0a14e9853b69b6d8528023` | `majority_disagree` after rotations (`nondet_disagree` majorities) |
| 4 | B | `0xff71de979775f730879c12bcbbdf88d97e42b07fcab8c20eac484a1face3073a` | majority_timeout (1 agree, 1 disagree, 3 timeout) |
| 5 | B | `0xbde24323568dd5062ab7f5126b861170a3371f7a1da675cf337facc201afe92e` | majority_timeout (2 disagree, 3 timeout) |

The only code change between B and C is the equivalence principle: verdicts
must fall in the same **decision group** (`{ON_SCOPE, MINOR_DRIFT}`, `{MAJOR_DRIFT}`,
`{UNKNOWN}`) instead of matching exactly — aligning consensus with the only
boundary the contract actually acts on (only `MAJOR_DRIFT` changes state).

**Observed result on instance C** (one controlled attempt, first try):

| Step | Tx | Consensus | Result |
|---|---|---|---|
| `assess(GovernorVotes.sol)` | `0xeac3630394c1f337cd490ebb3b259aec3fffd6d9d8a90c667ee732070e712019` | AGREE (3 agree, 1 timeout, 1 nondet_disagree) | `ON_SCOPE`, state `MONITORING`, history 1 entry |

This is a single observed deployment result: one transaction, submitted once,
ratified on the first attempt under the grouped principle, where five earlier
attempts under the exact-match principle had not been ratified. It is **not**
a success-rate measurement — no repeated-trial statistics were collected, and
validator timeouts and disagreements (one validator still disagreed here)
remain a live network property. The change is consistent with the hypothesis
that exact-match equivalence was part of the earlier failure mode; it does not
by itself prove it was the whole cause.

## Quick Demo

**DEMO 1 — honest deliverable** (instance C, live tx above):

```
GovernorVotes.sol  ──assess──▶  consensus AGREE  ──▶  ON_SCOPE  ──▶  MONITORING
```

**DEMO 2 — drifted deliverable** (instance A, live txs above):

```
Linux README  ──assess──▶  MAJOR_DRIFT  ──▶  REVIEW
                                   │
              non-funder resolve ✖ rejected ("only the funder…")
                                   │
              funder resolve_review("CANCEL") ──▶  CANCELLED
```

Run it yourself against any instance:

```bash
genlayer call  <address> get_state   --rpc https://rpc-bradbury.genlayer.com
genlayer call  <address> get_history --rpc https://rpc-bradbury.genlayer.com
```

## Limitations / Future Work

**Current MVP limitations** (not implemented, stated plainly):

- **Manual trigger** — every assessment is a submitted `assess` tx; there is no
  keeper, cron or event-driven automation.
- **Single contract, single grant** — one ScopeGuard instance per
  scope-of-work; no registry or batch tooling.
- **No fund custody** — the contract records verdicts and holds a REVIEW state,
  but it does not hold, escrow or tranche funds itself.
- **Validator LLM/web timeouts can still block ratification** — a tx needs a
  majority of validators to complete; observed Bradbury validators time out on
  LLM transactions often enough that any single submission may fail.
- **One observed leader parsing error remains** — a single on-scope attempt on
  instance A failed with a leader exit-code-1 error (most plausibly an LLM
  response that the strict JSON parse rejected). No guard has been added; a
  malformed model response still reverts the transaction. (Fail-closed: it
  cannot corrupt state, only fail the tx.)
- **Explorer indexing** — the Bradbury explorer's per-contract pages may not
  index the deployed instances; verification is done through transaction
  receipts and RPC reads.

**Future work** (design directions, none of it built):

- Multi-artifact and weighted rubrics.
- Proper `UNKNOWN` / fetch-failure handling (e.g. retries, distinct state).
- Tranche / fund-custody integration so REVIEW actually gates payments.
- Appeals and review UX for funders.
- A read-only frontend over `get_state` / `get_history`.
