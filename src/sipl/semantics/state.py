from __future__ import annotations

import re
from typing import Iterator, Mapping

from ..diagnostics import Diagnostic, SiplError


class State(Mapping[str, int]):
    __slots__ = ("_d", "_h")

    def __init__(self, items: Mapping[str, int] | None = None, **kw: int):
        self._d = dict(items or {})
        self._d.update(kw)
        self._h = None

    def __getitem__(self, k: str) -> int:
        return self._d[k]

    def __iter__(self) -> Iterator[str]:
        return iter(self._d)

    def __len__(self) -> int:
        return len(self._d)

    def __hash__(self):
        if self._h is None:
            self._h = hash(frozenset(self._d.items()))
        return self._h

    def __eq__(self, other):
        return isinstance(other, Mapping) and self._d == dict(other)

    def overlay(self, other: Mapping[str, int]) -> State:
        d = dict(self._d)
        d.update(other)
        return State(d)

    def extends_to(self, other: Mapping[str, int]) -> bool:
        return all(k in other and other[k] == v for k, v in self._d.items())

    __le__ = extends_to

    def __str__(self) -> str:
        return "[" + ", ".join(f"{k}↦{v}" for k, v in self._d.items()) + "]"

    __repr__ = __str__


_PAIR = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|↦)\s*([-–−]?\d+)\s*$")


def parse_state(text: str) -> State:
    d: dict[str, int] = {}
    text = text.strip().strip("[]")
    if text.strip():
        for part in text.split(","):
            m = _PAIR.match(part)
            if not m:
                raise SiplError(Diagnostic(f"некоректний запис стану: «{part.strip()}»",
                                           hint="очікується формат M=8, N=16"))
            d[m.group(1)] = int(m.group(2).replace("–", "-").replace("−", "-"))
    return State(d)
