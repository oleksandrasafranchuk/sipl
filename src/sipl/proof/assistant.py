from __future__ import annotations

import itertools
import random
import re
from dataclasses import dataclass, field

from .. import ast as A
from ..diagnostics import Diagnostic, SiplError
from ..semantics import terms as T
from ..semantics.builder import sem_P, sem_S
from ..semantics.evaluator import Evaluator, Undefined
from ..semantics.state import State
from . import spec as S


@dataclass
class ProofSpec:
    pre: object = S.SBool(True)
    post: object = S.SBool(True)
    invariant: object | None = None
    variant: object | None = None
    bound: int = 0
    domain: dict[str, range] = field(default_factory=dict)
    default_domain: range = range(-3, 11)
    max_cases: int = 100_000
    max_steps: int = 20_000
    max_iter: int = 1_000
    seed: int = 2026
    texts: dict[str, str] = field(default_factory=dict)


_DOM = re.compile(r"^\s*(.+?)\s+in\s+([-–]?\d+)\s*\.\.\s*([-–]?\d+)\s*$")


def _int(s: str) -> int:
    return int(s.replace("–", "-"))


def parse_proof_spec(text: str) -> ProofSpec:
    ps = ProofSpec()
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            raise SiplError(Diagnostic(f"рядок {lineno}: очікується «ключ: значення»"))
        key, val = (p.strip() for p in line.split(":", 1))
        key = key.lower()
        try:
            if key in ("pre", "post", "invariant", "variant"):
                ps.texts[key] = val
                setattr(ps, key, S.parse_spec(val))
            elif key == "bound":
                ps.bound = _int(val)
            elif key == "domain":
                for part in val.split(";"):
                    if not part.strip():
                        continue
                    m = _DOM.match(part)
                    if not m:
                        raise ValueError(f"область «{part.strip()}» — очікується «M, N in 1..20»")
                    rng = range(_int(m.group(2)), _int(m.group(3)) + 1)
                    for name in m.group(1).split(","):
                        name = name.strip()
                        if name == "*":
                            ps.default_domain = rng
                        else:
                            ps.domain[name] = rng
            else:
                raise ValueError(f"невідомий ключ «{key}»")
        except SiplError as e:
            e.diagnostic.message = f"рядок {lineno}: {e.diagnostic.message}"
            raise
        except ValueError as e:
            raise SiplError(Diagnostic(f"рядок {lineno}: {e}"))
    return ps


class NotSymbolic(Exception):
    pass


def unfold(fs, Q, log: list[str] | None = None):
    if isinstance(fs, T.Id):
        if log is not None:
            log.append("AF_ID: Q(id(st)) = Q(st)")
        return Q
    if isinstance(fs, T.AS):
        a = S.from_term(fs.expr)
        if log is not None:
            log.append(f"AF_AS: Q(AS^{fs.var}({T.render(fs.expr)})(st)) = Q[{fs.var} ↦ {S.show(a)}]")
        return S.subst(Q, {fs.var: a})
    if isinstance(fs, T.SeqT):
        if log is not None:
            log.append("AF_SEQ: Q((fs1•fs2)(st)) = Q(fs2(fs1(st)))")
        return unfold(fs.first, unfold(fs.second, Q, log), log)
    if isinstance(fs, T.IFT):
        b = S.from_term(fs.cond)
        if log is not None:
            log.append(f"AF_IF: Q(IF(fb, fs1, fs2)(st)) = (fb ⇒ Q(fs1(st))) ∧ (¬fb ⇒ Q(fs2(st))), "
                       f"fb = {S.show(b)}")
        return S.SBin("AND", S.SBin("IMPL", b, unfold(fs.then, Q, log)),
                      S.SBin("IMPL", S.SUn("NOT", b), unfold(fs.orelse, Q, log)))
    raise NotSymbolic("тіло містить вкладений цикл — формула не розгортається, "
                      "твердження перевіряється обчисленням терму")


@dataclass
class Obligation:
    id: str
    title: str
    basis: str
    statement: str
    formula: str | None
    unfold_log: list[str] = field(default_factory=list)
    checked: int = 0
    vacuous: int = 0
    sampled: bool = False
    ok: bool = True
    counterexample: dict | None = None


@dataclass
class ProofReport:
    program_term: str
    decomposition: dict
    obligations: list[Obligation]
    runs: dict
    partial: bool | None
    total: bool | None
    notes: list[str]


def _flatten(stm) -> list:
    if isinstance(stm, A.Seq):
        return _flatten(stm.first) + _flatten(stm.second)
    if isinstance(stm, A.Block):
        return _flatten(stm.body)
    return [stm]


def _seq_term(terms_: list):
    if not terms_:
        return T.Id()
    t = terms_[0]
    for x in terms_[1:]:
        t = T.SeqT(t, x)
    return t


class ProofAssistant:
    def __init__(self, program: A.Program, spec: ProofSpec):
        self.program = program
        self.spec = spec
        self.term = sem_P(program)
        stmts = _flatten(program.body)
        loops = [i for i, s in enumerate(stmts) if isinstance(s, A.While)]
        self.has_loop = bool(loops)
        if loops:
            k = loops[0]
            self.f0 = _seq_term([sem_S(s) for s in stmts[:k]])
            self.loop_term: T.WH = sem_S(stmts[k])
            self.f2 = _seq_term([sem_S(s) for s in stmts[k + 1:]])
            if spec.invariant is None:
                raise SiplError(Diagnostic("для програми з циклом потрібне індуктивне твердження "
                                           "(ключ invariant:)",
                                           hint="твердження, що зберігається "
                                                "при кожному виконанні тіла циклу"))
        prog_vars = A.variables(program)
        spec_exprs = [e for e in (spec.pre, spec.post, spec.invariant, spec.variant) if e is not None]
        cur, olds = {}, {}
        for e in spec_exprs:
            S.free_vars(e, cur, olds)
        self.vars = list(dict.fromkeys(prog_vars + list(cur) + list(olds)))
        self.olds = list(olds)
        self.rng = random.Random(spec.seed)

    def dom(self, v: str) -> range:
        return self.spec.domain.get(v, self.spec.default_domain)

    def states(self, names: list[str]):
        doms = [self.dom(v) for v in names]
        total = 1
        for d in doms:
            total *= len(d)
        if total <= self.spec.max_cases:
            return itertools.product(*doms), total, False
        n = self.spec.max_cases
        return (tuple(self.rng.choice(d) for d in doms) for _ in range(n)), n, True

    def run(self, fs, st: State) -> State:
        return Evaluator(max_steps=self.spec.max_steps, trace=False).apply(fs, st)

    @staticmethod
    def holds(e, st, init) -> bool | None:
        try:
            return bool(S.evaluate(e, st, init))
        except S.SpecUndefined:
            return None

    def _split(self, values):
        n = len(self.vars)
        cur = State(dict(zip(self.vars, values[:n])))
        init = dict(cur)
        init.update(zip(self.olds, values[n:]))
        return cur, State(init)

    def _formula(self, fs, Q, ob: Obligation):
        try:
            log: list[str] = []
            f = unfold(fs, Q, log)
            ob.unfold_log = log
            return f
        except NotSymbolic as e:
            ob.unfold_log = [str(e)]
            return None

    def check(self, ob: Obligation, hyp, concl, fs=None, with_olds=True, measure=None,
              label: str = "f(st)"):
        names = self.vars + (self.olds if with_olds else [])
        it, total, sampled = self.states(names)
        ob.sampled = sampled
        for values in it:
            if with_olds:
                st, init = self._split(values)
            else:
                st = State(dict(zip(self.vars, values)))
                init = st
            h = self.holds(hyp, st, init)
            if not h:
                ob.vacuous += 1
                ob.checked += 1
                continue
            ob.checked += 1
            after = st
            if fs is not None:
                try:
                    after = self.run(fs, st)
                except Undefined as u:
                    if measure is not None or ob.id == "INIT":
                        ob.ok = False
                        ob.counterexample = {"state": dict(st), "init": dict(init),
                                             "explanation": f"fs(st)↑: {u.message}"}
                        return ob
                    ob.vacuous += 1
                    continue
            if measure is not None:
                t0 = self.holds_value(measure, st, init)
                t1 = self.holds_value(measure, after, init)
                if t0 is None or t1 is None or not t1 < t0:
                    ob.ok = False
                    ob.counterexample = {"state": dict(st), "init": dict(init),
                                         "after": dict(after), "afterLabel": label,
                                         "explanation": f"t(st) = {t0}, t(f(st)) = {t1}: "
                                                        "строгого спадання немає"}
                    return ob
                continue
            c = self.holds(concl, after, init)
            if not c:
                ob.ok = False
                ob.counterexample = {
                    "state": dict(st), "init": dict(init),
                    "after": dict(after) if fs is not None else None, "afterLabel": label,
                    "explanation": ("висновок хибний" if c is False else "висновок не визначений")
                                   + f": {S.show(concl)} на стані {after}"}
                return ob
        return ob

    @staticmethod
    def holds_value(e, st, init):
        try:
            return S.evaluate(e, st, init)
        except S.SpecUndefined:
            return None

    def direct_runs(self) -> dict:
        names = self.vars
        it, total, sampled = self.states(names)
        res = {"initialStates": 0, "satisfyPre": 0, "terminated": 0, "diverged": 0,
               "unknown": 0, "invariantViolations": 0, "postViolations": 0,
               "sampled": sampled, "maxIterations": 0, "counterexample": None}
        p, f = (self.loop_term.cond, self.loop_term.body) if self.has_loop else (None, None)
        for values in it:
            st0 = State(dict(zip(names, values)))
            res["initialStates"] += 1
            if not self.holds(self.spec.pre, st0, st0):
                continue
            res["satisfyPre"] += 1
            history = [st0]
            try:
                if not self.has_loop:
                    final = self.run(self.term, st0)
                else:
                    cur = self.run(self.f0, st0)
                    history.append(cur)
                    k, seen = 0, {cur}
                    while True:
                        if not self.holds(self.spec.invariant, cur, st0):
                            res["invariantViolations"] += 1
                            if res["counterexample"] is None:
                                res["counterexample"] = {
                                    "kind": "invariant", "initial": dict(st0), "iteration": k,
                                    "states": [dict(h) for h in history[-12:]],
                                    "explanation": f"Q хибне на ітерації {k} (стан {cur})"}
                            raise _Stop
                        cond = Evaluator(trace=False).apply(p, cur)
                        if not cond:
                            break
                        cur = self.run(f, cur)
                        k += 1
                        history.append(cur)
                        if cur in seen or k > self.spec.max_iter:
                            kind = "diverges" if cur in seen else "limit"
                            res["diverged" if kind == "diverges" else "unknown"] += 1
                            if res["counterexample"] is None:
                                res["counterexample"] = {
                                    "kind": "termination", "initial": dict(st0),
                                    "states": [dict(h) for h in history[-8:]],
                                    "explanation": ("стан повторився — цикл не завершується"
                                                    if kind == "diverges" else
                                                    f"перевищено ліміт {self.spec.max_iter} ітерацій "
                                                    "(завершуваність не встановлено)")}
                            raise _Stop
                        seen.add(cur)
                    res["maxIterations"] = max(res["maxIterations"], k)
                    final = self.run(self.f2, cur)
                res["terminated"] += 1
                if not self.holds(self.spec.post, final, st0):
                    res["postViolations"] += 1
                    if res["counterexample"] is None:
                        res["counterexample"] = {"kind": "post", "initial": dict(st0),
                                                 "final": dict(final),
                                                 "explanation": f"post хибне на результаті {final}"}
            except _Stop:
                pass
            except Undefined as u:
                res["diverged" if u.kind == "diverges" else "unknown"] += 1
                if res["counterexample"] is None:
                    res["counterexample"] = {"kind": "termination", "initial": dict(st0),
                                             "explanation": u.message}
        return res

    def prove(self) -> ProofReport:
        sp = self.spec
        obs: list[Obligation] = []
        notes = [
            f"Область перевірки D: " + ", ".join(
                f"{v} ∈ {self.dom(v).start}..{self.dom(v).stop - 1}" for v in self.vars) +
            (f"; old(·) ∈ ті самі області" if self.olds else ""),
            "Перевірка на скінченній області — не доведення для всіх цілих: успіх означає, що "
            "твердження не спростовано на D; кроки з символьними формулами слід обґрунтувати "
            "(див. звіт).",
        ]
        decomp: dict = {}
        if not self.has_loop:
            ob = Obligation("DIRECT", "Пряма перевірка (програма без циклу)", "формули композицій",
                            "pre(st) ⇒ post(sem_P(P)(st))", None)
            f = self._formula(self.term, sp.post, ob)
            ob.formula = S.show(S.SBin("IMPL", sp.pre, f)) if f is not None else None
            self.check(ob, sp.pre, sp.post, self.term, with_olds=False, label="sem_P(P)(st)")
            obs.append(ob)
            runs = self.direct_runs()
            ok = ob.ok and runs["postViolations"] == 0
            return ProofReport(T.render(self.term), decomp, obs, runs, ok, ok and runs["terminated"] ==
                               runs["satisfyPre"], notes)

        p, f = self.loop_term.cond, self.loop_term.body
        P = S.from_term(p)
        Q = sp.invariant
        decomp = {"F0": T.render(self.f0), "p": T.render(p), "f": T.render(f),
                  "F2": T.render(self.f2),
                  "scheme": "sem_P(P) = F0 • WH(p, f) • F2"}

        ob = Obligation("INIT", "Ініціалізація: Q виконується перед циклом",
                        "AF_SEQ; початок індукції за k",
                        "pre(st) ⇒ Q(F0(st))", None)
        fq = self._formula(self.f0, Q, ob)
        ob.formula = S.show(S.SBin("IMPL", sp.pre, fq)) if fq is not None else None
        self.check(ob, sp.pre, Q, self.f0, with_olds=False, label="F0(st)")
        obs.append(ob)

        ob = Obligation("BASE", "База індукції (k = 0)",
                        "NumItWH = 0 ⇔ p(st)↓=false, тоді WH(p,f)(st) = st",
                        "Q(st) ∧ ¬p(st) ⇒ post(F2(st))", None)
        fq = self._formula(self.f2, sp.post, ob)
        hyp = S.SBin("AND", Q, S.SUn("NOT", P))
        ob.formula = S.show(S.SBin("IMPL", hyp, fq)) if fq is not None else None
        self.check(ob, hyp, sp.post, self.f2, label="F2(st)")
        obs.append(ob)

        ob = Obligation("STEP", "Крок індукції (k → k+1): Q зберігається тілом циклу",
                        "p(st)↓=true, WH(p,f)(st) = WH(p,f)(f(st)), "
                        "NumItWH((p,f), f(st)) = NumItWH((p,f), st) – 1",
                        "Q(st) ∧ p(st) ⇒ Q(f(st))", None)
        hyp = S.SBin("AND", Q, P)
        fq = self._formula(f, Q, ob)
        ob.formula = S.show(S.SBin("IMPL", hyp, fq)) if fq is not None else None
        self.check(ob, hyp, Q, f)
        obs.append(ob)

        if sp.variant is not None:
            t = sp.variant
            ob = Obligation("BOUND", "Обмеженість знизу",
                            "t обмежена знизу при істинній умові циклу",
                            f"Q(st) ∧ p(st) ⇒ t(st) ≥ {sp.bound},  t = {S.show(t)}",
                            S.show(S.SBin("IMPL", hyp, S.SBin(">=", t, S.SNum(sp.bound)))))
            self.check(ob, hyp, S.SBin(">=", t, S.SNum(sp.bound)))
            obs.append(ob)

            ob = Obligation("DECR", "Строге спадання",
                            "t0 > t1 > t2 > …",
                            f"Q(st) ∧ p(st) ⇒ t(f(st)) < t(st),  t = {S.show(t)}", None)
            fq = self._formula(f, S.SBin("<", t, S.SFrozen(t)), ob)
            ob.formula = S.show(S.SBin("IMPL", hyp, fq)) if fq is not None else None
            if fq is not None:
                ob.unfold_log.append("⟦t⟧ — значення t у стані st до виконання тіла "
                                     "(при підстановці не змінюється)")
            self.check(ob, hyp, None, f, measure=t)
            obs.append(ob)

        runs = self.direct_runs()
        by = {o.id: o.ok for o in obs}
        partial = by["INIT"] and by["BASE"] and by["STEP"] and runs["invariantViolations"] == 0 \
            and runs["postViolations"] == 0
        total = None
        if sp.variant is not None:
            total = partial and by["BOUND"] and by["DECR"] and runs["diverged"] == 0 \
                and runs["unknown"] == 0
        else:
            notes.append("Вираз t (variant) не задано — повна коректність не перевіряється.")
        return ProofReport(T.render(self.term), decomp, obs, runs, partial, total, notes)


class _Stop(Exception):
    pass


def _st(d: dict | None) -> str:
    return "—" if d is None else "[" + ", ".join(f"{k}↦{v}" for k, v in d.items()) + "]"


def render_report(rep: ProofReport, spec: ProofSpec) -> str:
    L: list[str] = ["Звіт перевірки коректності", ""]
    L.append(f"Семантичний терм: {rep.program_term}")
    if rep.decomposition:
        d = rep.decomposition
        L.append(f"Розклад: {d['scheme']}")
        for k in ("F0", "p", "f", "F2"):
            L.append(f"   {k} = {d[k]}")
    L.append("")
    L.append("── Специфікація")
    for k, name in (("pre", "передумова"), ("invariant", "інваріант Q"),
                    ("post", "післяумова"), ("variant", "спадна величина t")):
        if k in spec.texts:
            L.append(f"   {name}: {spec.texts[k]}")
    if spec.variant is not None:
        L.append(f"   нижня межа t: {spec.bound}")
    L.append("")
    L.append("── Перевірні кроки")
    for o in rep.obligations:
        L.append("")
        L.append(f"{'✔' if o.ok else '✘'} [{o.id}] {o.title}")
        L.append(f"   обґрунтування: {o.basis}")
        L.append(f"   треба:   {o.statement}")
        if o.unfold_log:
            L.append("   розгортання:")
            for s in o.unfold_log:
                L.append(f"     · {s}")
        if o.formula:
            L.append(f"   формула: {o.formula}")
        how = "випадкова вибірка" if o.sampled else "усі стани області"
        L.append(f"   перевірено станів: {o.checked} ({how}; засновок хибний: {o.vacuous})")
        if o.counterexample:
            ce = o.counterexample
            L.append("   КОНТРПРИКЛАД:")
            line = f"     st = {_st(ce.get('state'))}"
            if ce.get("init") != ce.get("state"):
                line += f",  old = {_st(ce.get('init'))}"
            L.append(line)
            if ce.get("after") is not None and ce.get("after") != ce.get("state"):
                L.append(f"     {ce.get('afterLabel', 'f(st)')} = {_st(ce.get('after'))}")
            L.append(f"     {ce['explanation']}")
    L.append("")
    r = rep.runs
    L.append("── Пряма перевірка запуском")
    L.append(f"   початкових станів: {r['initialStates']}, задовольняють передумову: {r['satisfyPre']}")
    L.append(f"   завершилися: {r['terminated']}; не завершуються: {r['diverged']}; "
             f"невідомо (ліміт): {r['unknown']}; макс. ітерацій: {r['maxIterations']}")
    L.append(f"   порушень інваріанта: {r['invariantViolations']}; порушень післяумови: {r['postViolations']}")
    if r["counterexample"]:
        ce = r["counterexample"]
        L.append(f"   КОНТРПРИКЛАД: початковий стан {_st(ce.get('initial'))}")
        if ce.get("states"):
            L.append("     стани: " + " → ".join(_st(s) for s in ce["states"]))
        L.append(f"     {ce['explanation']}")
    L.append("")
    L.append("── Висновок")
    verdict = {True: "не спростовано ✔", False: "спростовано ✘", None: "не перевірялась"}
    L.append(f"   часткова коректність: {verdict[rep.partial]}")
    L.append(f"   повна коректність:    {verdict[rep.total]}")
    for n in rep.notes:
        L.append(f"   примітка: {n}")
    return "\n".join(L)


def prove(program: A.Program, spec: ProofSpec) -> ProofReport:
    return ProofAssistant(program, spec).prove()
