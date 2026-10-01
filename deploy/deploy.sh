#!/usr/bin/env bash
# Deploy ScopeGuard to a GenLayer network using the genlayer CLI (v0.39.x).
#
# The CLI runs on Python 3.10+, unlike the gltest/genlayer_py toolchain, so this
# is the supported deploy path in constrained environments.
#
# Usage:
#   ./deploy/deploy.sh
#
# Configuration (env or .env — see .env.example):
#   GENLAYER_RPC       RPC URL (default: Bradbury testnet)
#   GENLAYER_ACCOUNT   keystore account NAME to deploy from (becomes `funder`)
#
# Constructor args: (scope_text: str, allowed_urls: list[str])
#   Edit SCOPE and ALLOWED_URLS below for your grant/bounty.
#
# NOTE: the CLI unlocks the keystore via the OS keychain or an INTERACTIVE
# password prompt. In headless environments without a keychain, set
# GENLAYER_PASSWORD_FILE to a 600-perm file holding the keystore password;
# this script then feeds it to the deploy prompt over stdin. The password is
# never printed or passed on the command line.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

# Load .env if present.
if [[ -f "$ROOT/.env" ]]; then
  set -a; # shellcheck disable=SC1091
  source "$ROOT/.env"; set +a
fi

RPC="${GENLAYER_RPC:-https://rpc-bradbury.genlayer.com}"
ACCOUNT="${GENLAYER_ACCOUNT:-uniformity}"
CONTRACT="$ROOT/contracts/scope_guard.py"

# --- Constructor arguments (edit for your deployment) ------------------------
SCOPE="Build an on-chain voting module: Solidity/Python smart contracts for token-weighted proposals, plus documentation and tests."
# JSON array of allow-listed artifact URLs the validators may fetch.
# Demo pair: [0] on-scope (governance/voting contracts docs), [1] clearly
# off-scope (Linux kernel README). Override with the ALLOWED_URLS env var.
ALLOWED_URLS="${ALLOWED_URLS:-[\"https://raw.githubusercontent.com/OpenZeppelin/openzeppelin-contracts/master/contracts/governance/README.adoc\", \"https://raw.githubusercontent.com/torvalds/linux/master/README\"]}"

echo "Deploying ScopeGuard"
echo "  contract : $CONTRACT"
echo "  rpc      : $RPC"
echo "  account  : $ACCOUNT"
echo

# Make sure the target account is the active one.
genlayer account use "$ACCOUNT" >/dev/null 2>&1 || true

# Feed the keystore password over stdin when a password file is configured
# (headless path); otherwise fall back to the CLI's interactive prompt/keychain.
deploy() {
  genlayer deploy \
    --contract "$CONTRACT" \
    --rpc "$RPC" \
    --args "$SCOPE" "$ALLOWED_URLS"
}

if [[ -n "${GENLAYER_PASSWORD_FILE:-}" && -f "$ROOT/$GENLAYER_PASSWORD_FILE" ]]; then
  { cat "$ROOT/$GENLAYER_PASSWORD_FILE"; echo; } | deploy
else
  deploy
fi
