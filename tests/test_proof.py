import pytest
from conftest import EXAMPLES

from sipl.diagnostics import SiplError
from sipl.parser import parse_program
from sipl.proof import spec as S
from sipl.proof.assistant import parse_proof_spec, prove, render_report, unfold
from sipl.semantics.builder import sem_S

GOOD = ["gcd", "power", "factorial", "mult", "divmod", "parity", "sub_by_one", "three_pow"]


def run(prog, spec_text, **kw):
    src = (EXAMPLES / f"{prog}.sipl").read_text(encoding="utf-8") if not prog.startswith("begin") else prog
    sp = parse_proof_spec(spec_text)
    for k, v in kw.items():
        setattr(sp, k, v)
    return prove(parse_program(src), sp), sp


@pytest.mark.parametrize("name", GOOD)
def test_examples_total_correctness(name):
    rep, _ = run(name, (EXAMPLES / f"{name}.spec").read_text(encoding="utf-8"), max_cases=20_000)
    assert rep.partial is True and rep.total is True, [o.to_json() for o in rep.obligations]
    assert [o.id for o in rep.obligations] == ["INIT", "BASE", "STEP", "BOUND", "DECR"]


def test_gcd_step_formula_is_substitution():
    rep, _ = run("gcd", (EXAMPLES / "gcd.spec").read_text(encoding="utf-8"), max_cases=5000)
    step = next(o for o in rep.obligations if o.id == "STEP")
    assert "gcd(M – N, N)" in step.formula and "gcd(M, N – M)" in step.formula
    assert any(s.startswith("AF_IF") for s in step.unfold_log)


def test_wrong_spec_gives_counterexample():
    rep, sp = run("gcd", (EXAMPLES / "gcd_wrong.spec").read_text(encoding="utf-8"))
    assert rep.partial is False and rep.total is False
    base = next(o for o in rep.obligations if o.id == "BASE")
    assert not base.ok and base.counterexample["state"]["M"] <= 0
    assert rep.runs["diverged"] > 0
    assert "КОНТРПРИКЛАД" in render_report(rep, sp)


def test_non_inductive_invariant_fails_step():
    spec = "pre: N >= 0\ninvariant: E = 1\npost: E = 1\ndomain: N, K in 0..5; E in 0..1"
    rep, _ = run("parity", spec)
    ob = {o.id: o for o in rep.obligations}
    assert ob["INIT"].ok and not ob["STEP"].ok
    ce = ob["STEP"].counterexample
    assert ce["state"]["E"] == 1 and ce["after"]["E"] == 0
    assert rep.runs["counterexample"]["kind"] == "invariant"


def test_bad_variant_fails_decr():
    spec = (EXAMPLES / "power.spec").read_text(encoding="utf-8").replace("variant:   Y", "variant:   R")
    rep, _ = run("power", spec)
    assert next(o for o in rep.obligations if o.id == "DECR").ok is False
    assert rep.total is False and rep.partial is True


def test_partial_only_without_variant():
    spec = "\n".join(l for l in (EXAMPLES / "factorial.spec").read_text(encoding="utf-8").splitlines()
                     if not l.startswith(("variant", "bound")))
    rep, _ = run("factorial", spec)
    assert rep.partial is True and rep.total is None


def test_loop_free_program_direct_check():
    rep, _ = run("max", (EXAMPLES / "max.spec").read_text(encoding="utf-8"))
    assert rep.partial and rep.obligations[0].id == "DIRECT"
    rep, _ = run("max", "post: Z = X\ndomain: X, Y, Z in -2..2")
    assert rep.partial is False


def test_unfold_assignment_is_substitution():
    stm = parse_program("begin X:=X+1; Y:=X*2 end").body
    f = unfold(sem_S(stm), S.parse_spec("Y > X"))
    assert S.show(f) == "(X + 1) * 2 > X + 1"


def test_spec_language():
    e = S.parse_spec("a >= 0 and gcd(a, b) = 1 -> ¬(a < b) ∨ old(a) ≠ 2")
    assert S.evaluate(e, {"a": 3, "b": 2}, {"a": 2}) is True
    assert S.evaluate(e, {"a": 3, "b": 4}, {"a": 2}) is False
    for bad in ("a >", "foo(1)", "old(1)", "gcd(1)"):
        with pytest.raises(SiplError):
            S.parse_spec(bad)


def test_spec_file_errors():
    with pytest.raises(SiplError, match="рядок 1"):
        parse_proof_spec("unknown: 1")
    with pytest.raises(SiplError, match="область"):
        parse_proof_spec("domain: M from 1 to 3")
    with pytest.raises(SiplError, match="invariant"):
        prove(parse_program("begin while X>0 do X:=X-1 end"), parse_proof_spec("post: X = 0"))
