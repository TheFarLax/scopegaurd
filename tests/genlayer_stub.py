"""
Lightweight stub of the GenLayer contract runtime for LOCAL testing only.

This is NOT the real GenVM. It mimics just enough of the `genlayer` module API
that `contracts/scope_guard.py` uses, so the contract's *deterministic* logic and
its handling of *mocked* non-deterministic results (web + LLM) can be exercised
with plain pytest — without Docker, a localnet, or a funded account.

What it faithfully simulates:
  - storage field auto-initialization (annotated fields start zero-valued)
  - @gl.public.write / @gl.public.view / @allow_storage decorators (identity)
  - gl.message.sender_address
  - gl.nondet.web.render(url, mode=...) via a page registry (set by the test)
  - gl.nondet.exec_prompt(prompt) via a responder callable (set by the test)
  - gl.eq_principle.prompt_comparative(fn, principle=...): runs fn() once and
    returns it (models the all-validators-agree happy path)

What it does NOT simulate: real multi-validator consensus, disagreement,
appeals, fees, or the GenVM sandbox. Those can only be verified on a network.
"""

from dataclasses import dataclass as _dataclass

__all__ = [
    "gl",
    "Address",
    "DynArray",
    "TreeMap",
    "u256",
    "u32",
    "i64",
    "bigint",
    "allow_storage",
    "dataclass",
]

dataclass = _dataclass

# --- storage type stand-ins --------------------------------------------------
u256 = int
u32 = int
i64 = int
bigint = int


class DynArray(list):
    def __class_getitem__(cls, item):
        return cls


class TreeMap(dict):
    def __class_getitem__(cls, item):
        return cls

    def get_or_insert_default(self, key):
        if key not in self:
            self[key] = TreeMap()
        return self[key]


class Address:
    ZERO = "0x" + "0" * 40

    def __init__(self, h=None):
        self._h = (h or Address.ZERO).lower()

    @property
    def as_hex(self):
        return self._h

    def __eq__(self, other):
        return isinstance(other, Address) and other._h == self._h

    def __hash__(self):
        return hash(self._h)

    def __repr__(self):
        return f"Address({self._h})"


def allow_storage(cls):
    return cls


# --- zero-value initialization for annotated storage fields ------------------
def _zero_for(annotation):
    if annotation in (DynArray,):
        return DynArray()
    if annotation in (TreeMap,):
        return TreeMap()
    if annotation is Address:
        return Address()
    if annotation is bool:
        return False
    if annotation is str:
        return ""
    if annotation in (int,):  # u256/u32/... are aliases of int
        return 0
    return None


class _Contract:
    """Base for gl.Contract: auto-initializes annotated storage fields."""

    def __new__(cls, *args, **kwargs):
        inst = super().__new__(cls)
        anns = {}
        for klass in reversed(cls.__mro__):
            anns.update(getattr(klass, "__annotations__", {}) or {})
        for name, ann in anns.items():
            setattr(inst, name, _zero_for(ann))
        return inst


# --- the `gl` facade ---------------------------------------------------------
class _PublicNS:
    @staticmethod
    def write(fn):
        return fn

    @staticmethod
    def view(fn):
        return fn


class _Message:
    def __init__(self):
        self.sender_address = Address()
        self.contract_address = Address()


class _Web:
    """Page registry: tests populate `pages[url] = "text"`."""

    def __init__(self):
        self.pages = {}

    def render(self, url, mode="text"):
        if url not in self.pages:
            raise Exception(f"stub web: no page registered for {url}")
        return self.pages[url]

    def get(self, url):
        return self.render(url)


class _Nondet:
    def __init__(self):
        self.web = _Web()
        # responder(prompt) -> raw LLM string. Overridable by tests.
        self.responder = lambda prompt: '{"verdict": "ON_SCOPE", "cites_scope": true, "rationale": "ok"}'

    def exec_prompt(self, prompt, **kwargs):
        return self.responder(prompt)


class _EqPrinciple:
    def __init__(self):
        # Last principle string passed in, so tests can inspect it.
        self.last_principle = None

    def strict_eq(self, fn):
        return fn()

    def prompt_comparative(self, fn, principle=None):
        # All honest validators agree -> the leader's result stands.
        self.last_principle = principle
        return fn()

    def prompt_non_comparative(self, fn, task=None, criteria=None):
        return fn()


class _GL:
    Contract = _Contract
    public = _PublicNS()

    def __init__(self):
        self.message = _Message()
        self.nondet = _Nondet()
        self.eq_principle = _EqPrinciple()

    class UserError(Exception):
        pass


gl = _GL()

