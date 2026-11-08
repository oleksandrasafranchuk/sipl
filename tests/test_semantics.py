import pytest
from conftest import EXAMPLES, GOLDEN

from sipl import ast as A
from sipl.parser import parse_program
from sipl.semantics import terms as T
from sipl.semantics.builder import sem_A, sem_P
from sipl.semantics.evaluator import evaluate, run
from sipl.semantics.state import State, parse_state

GCD = "begin\n  while ¬M=N do\n    if M>N then M:=M–N else N:=N–M\nend"
GCD_TERM = ("WH(S¹(neg, S²(eq, M⇒, N⇒)), IF(S²(gr, M⇒, N⇒), "
            "AS^M(S²(sub, M⇒, N⇒)), AS^N(S²(sub, N⇒, M⇒))))")


def term_of(src):
    return sem_P(parse_program(src))


def test_expression_term():
    e = parse_program("begin R:=X+Y*Z end").body.expr
    assert T.render(sem_A(e)) == "S²(add, X⇒, S²(mult, Y⇒, Z⇒))"


def test_gcd_term():
    assert T.render(term_of(GCD)) == GCD_TERM


def test_all_statement_rules():
    src = "begin X:=1; begin skip end; if (X>0) then X:=(X) else skip; while ¬X=0 ∨ X>9 do X:=X-1 end"
    assert T.render(term_of(src)) == (
        "AS^X(1̅) • id • IF(S²(gr, X⇒, 0̅), AS^X(X⇒), id) • "
        "WH(S²(or, S¹(neg, S²(eq, X⇒, 0̅)), S²(gr, X⇒, 9̅)), AS^X(S²(sub, X⇒, 1̅)))")


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.sipl")), ids=lambda p: p.stem)
def test_golden_terms(path):
    expected = (GOLDEN / f"{path.stem}.term").read_text(encoding="utf-8").strip()
    assert T.render(term_of(path.read_text(encoding="utf-8"))) == expected


def test_gcd_evaluation_and_trace():
    r = evaluate(term_of(GCD), parse_state("M=8, N=16"), trace=True)
    assert r.defined is True and r.value == State(M=8, N=8)
    rules = [e.rule for e in r.trace]
    assert rules[0] == "AF_WH"
    assert {"AF_S", "AF_IF", "AF_AS", "AF_DNM"} <= set(rules)


def test_overlay_and_extension():
    st = State(M=8, N=16).overlay(State(M=3, X=4, Y=2))
    assert st == State(M=3, N=16, X=4, Y=2) and list(st) == ["M", "N", "X", "Y"]
    assert State(M=8, N=16) <= State(M=8, X=4, Y=2, N=16)
    assert not State(M=8) <= State(M=9)


def test_undefined_variable():
    r = evaluate(term_of(GCD), parse_state("M=8"))
    assert r.defined is False and r.kind == "deref" and "N" in r.reason


def test_infinite_loop_detected():
    r = evaluate(term_of(GCD), parse_state("M=0, N=3"))
    assert r.defined is False and r.kind == "diverges"


def test_step_limit_gives_unknown():
    r = evaluate(term_of("begin while X>0 do X:=X+1 end"), parse_state("X=1"), max_steps=500)
    assert r.defined is None and r.kind == "limit"


def test_equal_negative_values_stop_unchanged():
    assert run(term_of(GCD), parse_state("M=-5, N=-5")) == State(M=-5, N=-5)


def test_extra_variable_does_not_change_result():
    assert run(term_of(GCD), State(M=8, N=16, L=9)) == State(M=8, N=8, L=9)
    for f in EXAMPLES.glob("*.sipl"):
        src = f.read_text(encoding="utf-8")
        t = term_of(src)
        names = sorted(A.variables(parse_program(src)))
        st = State({n: (i % 4) + 1 for i, n in enumerate(names)})
        r1 = run(t, st, max_steps=5000)
        r2 = run(t, st.overlay({"EXTRA": 42}), max_steps=5000)
        assert r1 <= r2 and r2["EXTRA"] == 42


def test_loop_unfolding_identity():
    t = term_of(GCD)
    unfolded = T.IFT(t.cond, T.SeqT(t.body, t), T.Id())
    for m in range(1, 9):
        for n in range(1, 9):
            st = State(M=m, N=n)
            assert run(t, st) == run(unfolded, st)


def test_seq_associativity():
    a, b, c = (T.AS("X", T.Sup("add", (T.Deref("X"), T.Const(k)))) for k in (1, 2, 3))
    for x in range(-3, 4):
        st = State(X=x)
        assert run(T.SeqT(T.SeqT(a, b), c), st) == run(T.SeqT(a, T.SeqT(b, c)), st)


@pytest.mark.parametrize("name,state,var,expected", [
    ("power", "X=2, Y=10", "R", 1024),
    ("factorial", "N=6", "F", 720),
    ("mult", "X=7, Y=6", "Z", 42),
    ("divmod", "X=17, Y=5", "Q", 3),
    ("divmod", "X=17, Y=5", "R", 2),
    ("parity", "N=7", "E", 0),
    ("parity", "N=10", "E", 1),
    ("sub_by_one", "X=3, Y=5", "Z", -2),
    ("three_pow", "X=4", "P", 81),
    ("max", "X=3, Y=9", "Z", 9),
])
def test_examples_compute(name, state, var, expected):
    src = (EXAMPLES / f"{name}.sipl").read_text(encoding="utf-8")
    assert run(term_of(src), parse_state(state))[var] == expected


def test_parse_state():
    assert parse_state("[M↦8, N↦–16]") == State(M=8, N=-16)
    assert parse_state("") == State()
