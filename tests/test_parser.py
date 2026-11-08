import pytest
from conftest import EXAMPLES

from sipl import ast as A
from sipl.diagnostics import SiplSyntaxError
from sipl.parser import check, parse, parse_program

GCD = """begin
  while ¬M=N do
    if M>N then M:=M–N else N:=N–M
end"""

POSITIVE = [
    "begin skip end",
    "begin X:=1 end",
    "begin X:=-1 end",
    "begin X:=1; Y:=2; Z:=3 end",
    "begin begin X:=1 end end",
    "begin if X>0 then X:=1 else skip end",
    "begin while X>0 do X:=X-1 end",
    "begin while not X=0 or X>5 do X:=X-1 end",
    "begin while ((X>1)) do X:=(X-1)*2 end",
    "begin if (X+1)>2 then skip else skip end",
    "begin X := A + B * C - (D - E) * 3 end",
    GCD,
    "begin R := 1; while Y > 0 do begin R := R * X; Y := Y - 1 end end",
    "begin X:=1 // коментар\nend",
    "begin while X>0 \\/ Y>0 do if X>0 then X:=X-1 else Y:=Y-1 end",
]

NEGATIVE = [
    ("begin X:=1; end", 1, 13, "після «;»"),
    ("X:=1", 1, 1, "«begin»"),
    ("begin X:=1", 1, 11, "«end»"),
    ("begin X=1 end", 1, 8, "«:=»"),
    ("begin if X>0 then X:=1 end", 1, 24, "«else»"),
    ("begin if X>0 then X:=1; Y:=2 else skip end", 1, 23, "«else»"),
    ("begin X:=-Y end", 1, 10, "унарний мінус"),
    ("begin X:=1 end end", 1, 16, "зайвий текст"),
    ("begin while X<0 do skip end", 1, 14, "невідомий символ"),
    ("begin X:= end", 1, 11, "арифметичний вираз"),
    ("begin while X do skip end", 1, 15, "«=», «>»"),
    ("begin 1X:=2 end", 1, 7, "з цифри"),
    ("begin end", 1, 7, "оператор"),
    ("begin X:=(1+2 end", 1, 15, "«)»"),
    ("begin while (X>1 do skip end", 1, 18, "«)»"),
    ("begin X:=1 Y:=2 end", 1, 12, "«;»"),
]


@pytest.mark.parametrize("src", POSITIVE)
def test_positive(src):
    assert check(src) == []
    assert isinstance(parse_program(src), A.Program)


@pytest.mark.parametrize("src,line,col,msg", NEGATIVE)
def test_negative(src, line, col, msg):
    with pytest.raises(SiplSyntaxError) as ei:
        parse(src)
    d = ei.value.diagnostic
    assert (d.span.line, d.span.col) == (line, col), d.render(src)
    assert msg in d.message, d.message


def test_diagnostic_render_has_caret_and_hint():
    src = "begin\n  X:=1;\nend"
    d = check(src)[0]
    text = d.render(src, "t.sipl")
    assert "t.sipl:3:1" in text and "^^^" in text and "підказка" in text


def test_ast_is_own_typed_nodes():
    p = parse_program(GCD)
    assert p == A.Program(A.While(
        A.Not(A.Cmp("=", A.Var("M"), A.Var("N"))),
        A.If(A.Cmp(">", A.Var("M"), A.Var("N")),
             A.Assign(A.Var("M"), A.BinA("-", A.Var("M"), A.Var("N"))),
             A.Assign(A.Var("N"), A.BinA("-", A.Var("N"), A.Var("M"))))))


def test_spans_point_to_source():
    src = GCD
    p = parse_program(src)

    def walk(n):
        assert n.span is not None and n.span.text(src).strip()
        for c in A.children(n):
            walk(c)
    walk(p.body)
    assign = p.body.body.then
    assert assign.span.text(src) == "M:=M–N"
    assert assign.expr.right.span.text(src) == "N"
    w = p.body
    assert (w.span.line, w.span.col, w.span.end_line) == (2, 3, 3)
    assert w.cond.span.text(src) == "¬M=N"


def test_priority_mult_over_add():
    e = parse_program("begin R:=X+Y*Z end").body.expr
    assert e == A.BinA("+", A.Var("X"), A.BinA("*", A.Var("Y"), A.Var("Z")))


def test_left_associativity():
    e = parse_program("begin R:=A-B-C end").body.expr
    assert e == A.BinA("-", A.BinA("-", A.Var("A"), A.Var("B")), A.Var("C"))


def test_seq_left_assoc_and_lowest_priority():
    s = parse_program("begin if B>0 then X:=1 else X:=2; Y:=3 end").body
    assert isinstance(s, A.Seq) and isinstance(s.first, A.If)
    s = parse_program("begin while B>0 do B:=B-1; Y:=3 end").body
    assert isinstance(s, A.Seq) and isinstance(s.first, A.While)
    s = parse_program("begin A:=1; B:=2; C:=3 end").body
    assert isinstance(s.first, A.Seq)


def test_not_binds_weaker_than_comparison_but_stronger_than_or():
    b = parse_program("begin while ¬X=1 ∨ Y>2 do skip end").body.cond
    assert b == A.Or(A.Not(A.Cmp("=", A.Var("X"), A.Num(1))), A.Cmp(">", A.Var("Y"), A.Num(2)))


def test_paren_ambiguity_backtracking():
    b = parse_program("begin while (X+1)>2 do skip end").body.cond
    assert isinstance(b, A.Cmp) and isinstance(b.left, A.ParenA)
    b = parse_program("begin while (X>1) ∨ (Y>1) do skip end").body.cond
    assert isinstance(b, A.Or) and isinstance(b.left, A.ParenB)


def test_negative_number_literal():
    e = parse_program("begin X:=Y--1 end").body.expr
    assert e == A.BinA("-", A.Var("Y"), A.Num(-1))


def test_all_examples_parse():
    files = sorted(EXAMPLES.glob("*.sipl"))
    assert len(files) >= 3
    for f in files:
        assert check(f.read_text(encoding="utf-8")) == [], f.name


def test_variables_order():
    assert A.variables(parse_program(GCD)) == ["M", "N"]
