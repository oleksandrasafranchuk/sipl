from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from .diagnostics import SourceSpan


def _span():
    return field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class Num:
    value: int
    span: SourceSpan | None = _span()


@dataclass(frozen=True)
class Var:
    name: str
    span: SourceSpan | None = _span()


@dataclass(frozen=True)
class BinA:
    op: str
    left: "Aexp"
    right: "Aexp"
    span: SourceSpan | None = _span()


@dataclass(frozen=True)
class ParenA:
    inner: "Aexp"
    span: SourceSpan | None = _span()


Aexp = Union[Num, Var, BinA, ParenA]


@dataclass(frozen=True)
class Cmp:
    op: str
    left: Aexp
    right: Aexp
    span: SourceSpan | None = _span()


@dataclass(frozen=True)
class Or:
    left: "Bexp"
    right: "Bexp"
    span: SourceSpan | None = _span()


@dataclass(frozen=True)
class Not:
    inner: "Bexp"
    span: SourceSpan | None = _span()


@dataclass(frozen=True)
class ParenB:
    inner: "Bexp"
    span: SourceSpan | None = _span()


Bexp = Union[Cmp, Or, Not, ParenB]


@dataclass(frozen=True)
class Assign:
    var: Var
    expr: Aexp
    span: SourceSpan | None = _span()


@dataclass(frozen=True)
class Seq:
    first: "Stm"
    second: "Stm"
    span: SourceSpan | None = _span()


@dataclass(frozen=True)
class If:
    cond: Bexp
    then: "Stm"
    orelse: "Stm"
    span: SourceSpan | None = _span()


@dataclass(frozen=True)
class While:
    cond: Bexp
    body: "Stm"
    span: SourceSpan | None = _span()


@dataclass(frozen=True)
class Block:
    body: "Stm"
    span: SourceSpan | None = _span()


@dataclass(frozen=True)
class Skip:
    span: SourceSpan | None = _span()


Stm = Union[Assign, Seq, If, While, Block, Skip]


@dataclass(frozen=True)
class Program:
    body: Stm
    span: SourceSpan | None = _span()


Node = Union[Aexp, Bexp, Stm, Program]


def children(node) -> list:
    if isinstance(node, (BinA, Cmp, Or)):
        return [node.left, node.right]
    if isinstance(node, (ParenA, ParenB, Not)):
        return [node.inner]
    if isinstance(node, Assign):
        return [node.var, node.expr]
    if isinstance(node, Seq):
        return [node.first, node.second]
    if isinstance(node, If):
        return [node.cond, node.then, node.orelse]
    if isinstance(node, While):
        return [node.cond, node.body]
    if isinstance(node, (Block, Program)):
        return [node.body]
    return []


def variables(node) -> list[str]:
    seen: dict[str, None] = {}

    def walk(n):
        if isinstance(n, Var):
            seen.setdefault(n.name, None)
        for c in children(n):
            walk(c)
    walk(node)
    return list(seen)
