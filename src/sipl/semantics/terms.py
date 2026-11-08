from __future__ import annotations

from dataclasses import dataclass

_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


@dataclass(frozen=True)
class Const:
    value: int


@dataclass(frozen=True)
class Deref:
    var: str


@dataclass(frozen=True)
class Sup:
    func: str
    args: tuple


@dataclass(frozen=True)
class AS:
    var: str
    expr: object


@dataclass(frozen=True)
class SeqT:
    first: object
    second: object


@dataclass(frozen=True)
class IFT:
    cond: object
    then: object
    orelse: object


@dataclass(frozen=True)
class WH:
    cond: object
    body: object


@dataclass(frozen=True)
class Id:
    pass


def render(t) -> str:
    if isinstance(t, Const):
        return "".join(ch + "̅" for ch in str(t.value))
    if isinstance(t, Deref):
        return f"{t.var}⇒"
    if isinstance(t, Sup):
        head = "S" + str(len(t.args)).translate(_SUPERSCRIPT)
        return f"{head}({t.func}, {', '.join(render(a) for a in t.args)})"
    if isinstance(t, AS):
        return f"AS^{t.var}({render(t.expr)})"
    if isinstance(t, SeqT):
        right = render(t.second)
        if isinstance(t.second, SeqT):
            right = f"({right})"
        return f"{render(t.first)} • {right}"
    if isinstance(t, IFT):
        return f"IF({render(t.cond)}, {render(t.then)}, {render(t.orelse)})"
    if isinstance(t, WH):
        return f"WH({render(t.cond)}, {render(t.body)})"
    if isinstance(t, Id):
        return "id"
    raise TypeError(t)
