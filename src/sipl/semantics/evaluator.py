from __future__ import annotations

from dataclasses import dataclass, field

from . import terms as T
from .state import State

_FUNCS = {
    "add": lambda a, b: a + b,
    "sub": lambda a, b: a - b,
    "mult": lambda a, b: a * b,
    "or": lambda a, b: a or b,
    "neg": lambda a: not a,
    "eq": lambda a, b: a == b,
    "gr": lambda a, b: a > b,
}

TERM_WIDTH = 80


def fmt_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def short(t) -> str:
    s = T.render(t)
    return s if len(s) <= TERM_WIDTH else s[:TERM_WIDTH - 1] + "…"


@dataclass
class TraceEvent:
    depth: int
    rule: str
    text: str
    result: str = ""

    def render(self) -> str:
        res = f" = {self.result}" if self.result else ""
        return f"{'  ' * self.depth}{self.rule:<7} {self.text}{res}"


class Undefined(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass
class EvalResult:
    defined: bool | None
    value: object = None
    kind: str | None = None
    reason: str | None = None
    steps: int = 0
    trace: list[TraceEvent] = field(default_factory=list)

    def summary(self) -> str:
        if self.defined:
            return f"значення визначене (↓): {self.value}"
        if self.defined is False:
            return f"значення не визначене (↑): {self.reason}"
        return f"визначеність не встановлено: {self.reason}"


class Evaluator:
    def __init__(self, max_steps: int = 200_000, trace: bool = False):
        self.max_steps = max_steps
        self.tracing = trace
        self.steps = 0
        self.events: list[TraceEvent] = []

    def emit(self, depth: int, rule: str, text: str) -> TraceEvent | None:
        if not self.tracing:
            return None
        ev = TraceEvent(depth, rule, text)
        self.events.append(ev)
        return ev

    def tick(self):
        self.steps += 1
        if self.steps > self.max_steps:
            raise Undefined("limit", f"перевищено ліміт у {self.max_steps} кроків; можливо, "
                                     "цикл не завершується, або ліміт замалий (--max-steps)")

    def apply(self, t, st: State, depth: int = 0):
        self.tick()
        if isinstance(t, T.Const):
            ev = self.emit(depth, "CONST", f"{short(t)}({st})")
            if ev:
                ev.result = str(t.value)
            return t.value
        if isinstance(t, T.Deref):
            ev = self.emit(depth, "AF_DNM", f"{short(t)}({st})")
            if t.var not in st:
                if ev:
                    ev.result = "↑"
                raise Undefined("deref", f"змінна {t.var} не має значення у стані {st}")
            if ev:
                ev.result = str(st[t.var])
            return st[t.var]
        if isinstance(t, T.Sup):
            ev = self.emit(depth, "AF_S", f"{short(t)}({st})")
            vals = [self.apply(a, st, depth + 1) for a in t.args]
            r = _FUNCS[t.func](*vals)
            if ev:
                ev.result = f"{t.func}({', '.join(fmt_value(v) for v in vals)}) = {fmt_value(r)}"
            return r
        if isinstance(t, T.AS):
            ev = self.emit(depth, "AF_AS", f"{short(t)}({st})")
            v = self.apply(t.expr, st, depth + 1)
            new = st.overlay({t.var: v})
            if ev:
                ev.result = f"{st} ∇ [{t.var}↦{v}] = {new}"
            return new
        if isinstance(t, T.SeqT):
            ev = self.emit(depth, "AF_SEQ", f"({short(t)})({st})")
            res = self.apply(t.second, self.apply(t.first, st, depth + 1), depth + 1)
            if ev:
                ev.result = str(res)
            return res
        if isinstance(t, T.IFT):
            ev = self.emit(depth, "AF_IF", f"{short(t)}({st})")
            c = self.apply(t.cond, st, depth + 1)
            res = self.apply(t.then if c else t.orelse, st, depth + 1)
            if ev:
                ev.result = f"[умова {fmt_value(c)}] {res}"
            return res
        if isinstance(t, T.WH):
            return self.apply_wh(t, st, depth)
        if isinstance(t, T.Id):
            ev = self.emit(depth, "AF_ID", f"id({st})")
            if ev:
                ev.result = str(st)
            return st
        raise TypeError(t)

    def apply_wh(self, t: T.WH, st: State, depth: int):
        ev = self.emit(depth, "AF_WH", f"{short(t)}({st})")
        seen = {st: 0}
        cur, i = st, 0
        while True:
            self.tick()
            it = self.emit(depth + 1, f"WH#{i}", f"st{i} = {cur}")
            c = self.apply(t.cond, cur, depth + 2)
            if it:
                it.text += f";  умова = {fmt_value(c)}"
            if not c:
                if ev:
                    ev.result = f"{cur}   (ітерацій: {i})"
                return cur
            cur = self.apply(t.body, cur, depth + 2)
            i += 1
            if cur in seen:
                if ev:
                    ev.result = "↑"
                raise Undefined("diverges", f"цикл не завершується: стан {cur} повторився "
                                            f"(st{i} = st{seen[cur]})")
            seen[cur] = i


def evaluate(term, state: State, max_steps: int = 200_000, trace: bool = False) -> EvalResult:
    ev = Evaluator(max_steps, trace)
    try:
        v = ev.apply(term, state)
        return EvalResult(True, v, steps=ev.steps, trace=ev.events)
    except Undefined as u:
        defined = None if u.kind == "limit" else False
        return EvalResult(defined, None, u.kind, u.message, ev.steps, ev.events)


def run(term, state: State, max_steps: int = 200_000):
    return Evaluator(max_steps).apply(term, state)
