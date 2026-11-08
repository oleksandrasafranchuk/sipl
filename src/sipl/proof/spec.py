from __future__ import annotations

import math
from dataclasses import dataclass

from ..diagnostics import Diagnostic, SiplError
from ..lexer import Token, tokenize
from ..semantics import terms as T


class SpecError(SiplError):
    pass


def _err(msg: str, tok: Token | None = None, hint: str | None = None):
    raise SpecError(Diagnostic(msg, tok.span if tok else None, hint=hint))


@dataclass(frozen=True)
class SNum:
    value: int


@dataclass(frozen=True)
class SBool:
    value: bool


@dataclass(frozen=True)
class SVar:
    name: str


@dataclass(frozen=True)
class SOld:
    name: str


@dataclass(frozen=True)
class SFrozen:
    expr: object


@dataclass(frozen=True)
class SUn:
    op: str
    e: object


@dataclass(frozen=True)
class SBin:
    op: str
    l: object
    r: object


@dataclass(frozen=True)
class SCall:
    name: str
    args: tuple


def _fact(n):
    if n < 0:
        raise ArithmeticError("fact від'ємного числа")
    return math.factorial(n)


def _pow(a, b):
    if b < 0:
        raise ArithmeticError("pow з від'ємним степенем")
    return a ** b


def _lg(n):
    if n <= 0:
        raise ArithmeticError("lg непозитивного числа")
    return len(str(n)) - 1


def _div(a, b):
    if b == 0:
        raise ZeroDivisionError("ділення на 0")
    return a // b


def _mod(a, b):
    if b == 0:
        raise ZeroDivisionError("ділення на 0")
    return a % b


FUNCS = {
    "gcd": (2, math.gcd), "abs": (1, abs), "min": (2, min), "max": (2, max),
    "fact": (1, _fact), "pow": (2, _pow), "div": (2, _div), "mod": (2, _mod),
    "lg": (1, _lg), "even": (1, lambda n: n % 2 == 0), "odd": (1, lambda n: n % 2 == 1),
}


class _SpecParser:
    def __init__(self, text: str):
        self.text = text
        self.toks = tokenize(text, extended=True)
        self.pos = 0

    @property
    def tok(self):
        return self.toks[self.pos]

    def at(self, kind, value=None):
        t = self.tok
        return t.kind == kind and (value is None or t.value == value)

    def eat(self, kind, value=None, what=None):
        if not self.at(kind, value):
            _err(f"очікувалось «{what or value or kind}», знайдено {self.tok.describe()} "
                 f"у специфікації «{self.text}»", self.tok)
        t = self.tok
        self.pos += 1
        return t

    def parse(self):
        e = self.impl()
        if not self.at("EOF"):
            _err(f"зайвий текст {self.tok.describe()} у специфікації «{self.text}»", self.tok)
        return e

    def impl(self):
        left = self.disj()
        if self.at("OP", "IMPL"):
            self.pos += 1
            return SBin("IMPL", left, self.impl())
        return left

    def disj(self):
        left = self.conj()
        while self.at("OP", "OR"):
            self.pos += 1
            left = SBin("OR", left, self.conj())
        return left

    def conj(self):
        left = self.neg()
        while self.at("OP", "AND"):
            self.pos += 1
            left = SBin("AND", left, self.neg())
        return left

    def neg(self):
        if self.at("OP", "NOT"):
            self.pos += 1
            return SUn("NOT", self.neg())
        return self.cmp()

    def cmp(self):
        left = self.add()
        for op in ("=", "!=", ">", "<", ">=", "<="):
            if self.at("OP", op):
                self.pos += 1
                return SBin(op, left, self.add())
        return left

    def add(self):
        left = self.mul()
        while self.at("OP", "+") or self.at("OP", "-"):
            op = self.tok.value
            self.pos += 1
            left = SBin(op, left, self.mul())
        return left

    def mul(self):
        left = self.unary()
        while self.at("OP", "*") or self.at("OP", "/") or self.at("OP", "%"):
            op = self.tok.value
            self.pos += 1
            left = SBin(op, left, self.unary())
        return left

    def unary(self):
        if self.at("OP", "-"):
            self.pos += 1
            e = self.unary()
            return SNum(-e.value) if isinstance(e, SNum) else SUn("NEG", e)
        return self.atom()

    def atom(self):
        t = self.tok
        if t.kind == "NUM":
            self.pos += 1
            return SNum(int(t.value))
        if t.kind == "KW" and t.value in ("true", "false"):
            self.pos += 1
            return SBool(t.value == "true")
        if t.kind == "IDENT":
            self.pos += 1
            if self.at("OP", "("):
                self.pos += 1
                args = [self.impl()]
                while self.at("OP", ","):
                    self.pos += 1
                    args.append(self.impl())
                self.eat("OP", ")")
                if t.value == "old":
                    if len(args) != 1 or not isinstance(args[0], SVar):
                        _err("old(…) приймає одну змінну, наприклад old(M)", t)
                    return SOld(args[0].name)
                if t.value not in FUNCS:
                    _err(f"невідома функція «{t.value}»", t,
                         "доступні: " + ", ".join(sorted(FUNCS)) + ", old")
                if FUNCS[t.value][0] != len(args):
                    _err(f"функція {t.value} очікує {FUNCS[t.value][0]} аргумент(и)", t)
                return SCall(t.value, tuple(args))
            return SVar(t.value)
        if t.kind == "OP" and t.value == "(":
            self.pos += 1
            e = self.impl()
            self.eat("OP", ")")
            return e
        _err(f"очікувався вираз, знайдено {t.describe()} у специфікації «{self.text}»", t)


def parse_spec(text: str):
    return _SpecParser(text).parse()


class SpecUndefined(Exception):
    pass


def evaluate(e, st, init=None):
    if isinstance(e, SNum):
        return e.value
    if isinstance(e, SBool):
        return e.value
    if isinstance(e, SVar):
        if e.name not in st:
            raise SpecUndefined(f"змінна {e.name} не має значення")
        return st[e.name]
    if isinstance(e, SOld):
        src = init if init is not None else st
        if e.name not in src:
            raise SpecUndefined(f"old({e.name}) не визначене")
        return src[e.name]
    if isinstance(e, SFrozen):
        return evaluate(e.expr, st, init)
    if isinstance(e, SUn):
        v = evaluate(e.e, st, init)
        return (not v) if e.op == "NOT" else -v
    if isinstance(e, SBin):
        op = e.op
        if op == "AND":
            return bool(evaluate(e.l, st, init)) and bool(evaluate(e.r, st, init))
        if op == "OR":
            return bool(evaluate(e.l, st, init)) or bool(evaluate(e.r, st, init))
        if op == "IMPL":
            return (not evaluate(e.l, st, init)) or bool(evaluate(e.r, st, init))
        a, b = evaluate(e.l, st, init), evaluate(e.r, st, init)
        try:
            return {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b,
                    "/": lambda: _div(a, b), "%": lambda: _mod(a, b),
                    "=": lambda: a == b, "!=": lambda: a != b, ">": lambda: a > b,
                    "<": lambda: a < b, ">=": lambda: a >= b, "<=": lambda: a <= b}[op]()
        except ArithmeticError as ex:
            raise SpecUndefined(str(ex))
    if isinstance(e, SCall):
        args = [evaluate(a, st, init) for a in e.args]
        try:
            return FUNCS[e.name][1](*args)
        except (ArithmeticError, ValueError) as ex:
            raise SpecUndefined(f"{e.name}: {ex}")
    raise TypeError(e)


def free_vars(e, acc=None, olds=None):
    acc = {} if acc is None else acc
    olds = {} if olds is None else olds
    if isinstance(e, SVar):
        acc.setdefault(e.name)
    elif isinstance(e, SOld):
        olds.setdefault(e.name)
    elif isinstance(e, SFrozen):
        free_vars(e.expr, acc, olds)
    elif isinstance(e, SUn):
        free_vars(e.e, acc, olds)
    elif isinstance(e, SBin):
        free_vars(e.l, acc, olds)
        free_vars(e.r, acc, olds)
    elif isinstance(e, SCall):
        for a in e.args:
            free_vars(a, acc, olds)
    return acc, olds


def subst(e, mapping: dict):
    if isinstance(e, SVar):
        return mapping.get(e.name, e)
    if isinstance(e, SUn):
        return SUn(e.op, subst(e.e, mapping))
    if isinstance(e, SBin):
        return SBin(e.op, subst(e.l, mapping), subst(e.r, mapping))
    if isinstance(e, SCall):
        return SCall(e.name, tuple(subst(a, mapping) for a in e.args))
    return e


_TFUNC = {"add": "+", "sub": "-", "mult": "*", "eq": "=", "gr": ">", "or": "OR"}


def from_term(t):
    if isinstance(t, T.Const):
        return SNum(t.value)
    if isinstance(t, T.Deref):
        return SVar(t.var)
    if isinstance(t, T.Sup):
        if t.func == "neg":
            return SUn("NOT", from_term(t.args[0]))
        return SBin(_TFUNC[t.func], from_term(t.args[0]), from_term(t.args[1]))
    raise TypeError(t)


_PREC = {"IMPL": 1, "OR": 2, "AND": 3, "NOT": 4, "=": 5, "!=": 5, ">": 5, "<": 5, ">=": 5,
         "<=": 5, "+": 6, "-": 6, "*": 7, "/": 7, "%": 7, "NEG": 8}
_SYM = {"IMPL": "⇒", "OR": "∨", "AND": "∧", "!=": "≠", ">=": "≥", "<=": "≤", "-": "–"}


def show(e, parent: int = 0) -> str:
    if isinstance(e, SNum):
        return str(e.value) if e.value >= 0 or parent == 0 else f"({e.value})"
    if isinstance(e, SBool):
        return "true" if e.value else "false"
    if isinstance(e, SVar):
        return e.name
    if isinstance(e, SOld):
        return f"old({e.name})"
    if isinstance(e, SFrozen):
        return f"⟦{show(e.expr)}⟧"
    if isinstance(e, SCall):
        return f"{e.name}({', '.join(show(a) for a in e.args)})"
    if isinstance(e, SUn):
        p = _PREC[e.op]
        inner = show(e.e, p)
        if e.op == "NOT" and isinstance(e.e, SBin) and _PREC[e.e.op] == 5:
            inner = f"({inner})"
        s = ("¬" if e.op == "NOT" else "–") + inner
        return f"({s})" if p < parent else s
    if isinstance(e, SBin):
        p = _PREC[e.op]
        right_p = p + 1 if e.op != "IMPL" else p
        left_p = p if e.op != "IMPL" else p + 1
        if p == 5:
            left_p = right_p = p + 1
        s = f"{show(e.l, left_p)} {_SYM.get(e.op, e.op)} {show(e.r, right_p)}"
        return f"({s})" if p < parent else s
    raise TypeError(e)
