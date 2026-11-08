from __future__ import annotations

from dataclasses import dataclass

from . import ast as A
from .diagnostics import Diagnostic, SiplSyntaxError
from .lexer import Token, tokenize
from .parse_tree import ParseNode


@dataclass
class ParseResult:
    source: str
    tree: ParseNode
    ast: A.Program


class _Parser:
    def __init__(self, source: str):
        self.source = source
        self.toks: list[Token] = tokenize(source)
        self.pos = 0

    @property
    def tok(self) -> Token:
        return self.toks[self.pos]

    def at(self, kind: str, value: str | None = None) -> bool:
        t = self.tok
        return t.kind == kind and (value is None or t.value == value)

    def error(self, message: str, hint: str | None = None, tok: Token | None = None):
        t = tok or self.tok
        raise SiplSyntaxError(Diagnostic(message, t.span,
                                         hint=hint))

    def expected_error(self, expected: list[str], hint: str | None = None):
        exp = ", ".join(f"«{e}»" for e in expected)
        self.error(f"очікувалось {exp}, але знайдено {self.tok.describe()}", hint)

    def term(self, kind: str, value: str | None = None, what: str | None = None) -> ParseNode:
        if not self.at(kind, value):
            self.expected_error([what or value or kind])
        t = self.tok
        self.pos += 1
        return ParseNode(t.text, t.span, terminal=True)

    @staticmethod
    def nt(symbol: str, rule: str, children: list[ParseNode]) -> ParseNode:
        span = children[0].span.merge(children[-1].span)
        return ParseNode(symbol, span, rule, children)

    def program(self) -> ParseNode:
        if not self.at("KW", "begin"):
            self.expected_error(["begin"], "програма SIPL має вигляд begin S end")
        b = self.term("KW", "begin")
        s = self.stm()
        if not self.at("KW", "end"):
            self.stm_tail_error()
        e = self.term("KW", "end")
        if not self.at("EOF"):
            self.error(f"зайвий текст після кінця програми: {self.tok.describe()}",
                       "програма — це один блок begin … end")
        return self.nt("<програма>", "NP1", [b, s, e])

    def stm_tail_error(self):
        t = self.tok
        hint = None
        if t.kind == "KW" and t.value == "else":
            hint = ("частина then містить лише один оператор (пріоритет «;» найнижчий); "
                    "для кількох операторів використайте begin … end")
        elif t.kind in ("IDENT", "KW") and t.value not in ("end",):
            hint = "оператори розділяються знаком «;»"
        self.expected_error(["end", ";"], hint)

    def stm(self) -> ParseNode:
        left = self.simple_stm()
        while self.at("OP", ";"):
            semi = self.term("OP", ";")
            if self.at("KW", "end"):
                self.error("після «;» очікувався оператор, а знайдено «end»",
                           "у SIPL «;» розділяє оператори (S1;S2), тому перед end крапка з комою "
                           "не ставиться")
            right = self.simple_stm()
            left = self.nt("<оператор>", "NS2", [left, semi, right])
        return left

    def simple_stm(self) -> ParseNode:
        t = self.tok
        if t.kind == "IDENT":
            x = self.var()
            if not self.at("OP", ":="):
                hint = "присвоєння записується «x := a»"
                if self.at("OP", "="):
                    hint = "для присвоєння використовуйте «:=», а не «=»"
                self.expected_error([":="], hint)
            assign = self.term("OP", ":=")
            a = self.aexp()
            return self.nt("<оператор>", "NS1", [x, assign, a])
        if t.kind == "KW":
            if t.value == "if":
                kw = self.term("KW", "if")
                b = self.bexp()
                th = self.term("KW", "then")
                s1 = self.simple_stm()
                if not self.at("KW", "else"):
                    hint = ("у SIPL умовний оператор завжди має else-гілку; "
                            "якщо гілка не потрібна, використайте «else skip»")
                    if self.at("OP", ";"):
                        hint = ("then-частина містить лише один оператор (пріоритет «;» найнижчий); "
                                "кілька операторів оберніть у begin … end")
                    self.expected_error(["else"], hint)
                el = self.term("KW", "else")
                s2 = self.simple_stm()
                return self.nt("<оператор>", "NS3", [kw, b, th, s1, el, s2])
            if t.value == "while":
                kw = self.term("KW", "while")
                b = self.bexp()
                do = self.term("KW", "do")
                s = self.simple_stm()
                return self.nt("<оператор>", "NS4", [kw, b, do, s])
            if t.value == "begin":
                b = self.term("KW", "begin")
                s = self.stm()
                if not self.at("KW", "end"):
                    self.stm_tail_error()
                e = self.term("KW", "end")
                return self.nt("<оператор>", "NS5", [b, s, e])
            if t.value == "skip":
                return self.nt("<оператор>", "NS6", [self.term("KW", "skip")])
        hint = None
        if t.kind == "KW" and t.value == "end":
            hint = "порожній оператор у SIPL записується як skip"
        self.error(f"очікувався оператор, але знайдено {t.describe()}", hint)

    def var(self) -> ParseNode:
        x = self.term("IDENT", what="змінна")
        return ParseNode("<змінна>", x.span, "NV", [x])

    def num(self) -> ParseNode:
        if self.at("OP", "-"):
            minus = self.tok
            self.pos += 1
            if not self.at("NUM"):
                self.error("унарний мінус допускається лише в записі числа",
                           "запишіть 0–a замість –a", tok=minus)
            digits = self.tok
            self.pos += 1
            span = minus.span.merge(digits.span)
            leaf = ParseNode(minus.text + digits.text, span, terminal=True)
            return ParseNode("<число>", span, "NN", [leaf])
        n = self.term("NUM", what="число")
        return ParseNode("<число>", n.span, "NN", [n])

    def aexp(self) -> ParseNode:
        left = self.aterm()
        while self.at("OP", "+") or self.at("OP", "-"):
            rule = "NA3" if self.tok.value == "+" else "NA4"
            op = self.term("OP")
            right = self.aterm()
            left = self.nt("<вираз>", rule, [left, op, right])
        return left

    def aterm(self) -> ParseNode:
        left = self.afactor()
        while self.at("OP", "*"):
            op = self.term("OP", "*")
            right = self.afactor()
            left = self.nt("<вираз>", "NA5", [left, op, right])
        return left

    def afactor(self) -> ParseNode:
        t = self.tok
        if t.kind == "NUM" or (t.kind == "OP" and t.value == "-"):
            n = self.num()
            return ParseNode("<вираз>", n.span, "NA1", [n])
        if t.kind == "IDENT":
            x = self.var()
            return ParseNode("<вираз>", x.span, "NA2", [x])
        if t.kind == "OP" and t.value == "(":
            lp = self.term("OP", "(")
            a = self.aexp()
            rp = self.term("OP", ")")
            return self.nt("<вираз>", "NA6", [lp, a, rp])
        self.error(f"очікувався арифметичний вираз, але знайдено {t.describe()}")

    def bexp(self) -> ParseNode:
        left = self.bunary()
        while self.at("OP", "OR"):
            op = self.term("OP", "OR")
            right = self.bunary()
            left = self.nt("<умова>", "NB3", [left, op, right])
        return left

    def bunary(self) -> ParseNode:
        if self.at("OP", "NOT"):
            op = self.term("OP", "NOT")
            b = self.bunary()
            return self.nt("<умова>", "NB4", [op, b])
        return self.batom()

    def batom(self) -> ParseNode:
        if self.at("OP", "("):
            save = self.pos
            try:
                return self.comparison()
            except SiplSyntaxError as e1:
                self.pos = save
                try:
                    lp = self.term("OP", "(")
                    b = self.bexp()
                    rp = self.term("OP", ")")
                    return self.nt("<умова>", "NB5", [lp, b, rp])
                except SiplSyntaxError as e2:
                    s1 = e1.diagnostic.span.start if e1.diagnostic.span else -1
                    s2 = e2.diagnostic.span.start if e2.diagnostic.span else -1
                    raise e1 if s1 > s2 else e2
        return self.comparison()

    def comparison(self) -> ParseNode:
        if not (self.at("NUM") or self.at("IDENT") or self.at("OP", "(") or self.at("OP", "-")):
            self.error(f"очікувалась умова, але знайдено {self.tok.describe()}")
        a1 = self.aexp()
        if not (self.at("OP", "=") or self.at("OP", ">")):
            self.expected_error(["=", ">"],
                                "умова SIPL — це a1=a2, a1>a2, b1∨b2, ¬b або (b)")
        rule = "NB1" if self.tok.value == "=" else "NB2"
        op = self.term("OP")
        a2 = self.aexp()
        return self.nt("<умова>", rule, [a1, op, a2])


def build_ast(node: ParseNode):
    r, ch, sp = node.rule, node.children, node.span
    if r == "NP1":
        return A.Program(build_ast(ch[1]), sp)
    if r == "NS1":
        return A.Assign(build_ast(ch[0]), build_ast(ch[2]), sp)
    if r == "NS2":
        return A.Seq(build_ast(ch[0]), build_ast(ch[2]), sp)
    if r == "NS3":
        return A.If(build_ast(ch[1]), build_ast(ch[3]), build_ast(ch[5]), sp)
    if r == "NS4":
        return A.While(build_ast(ch[1]), build_ast(ch[3]), sp)
    if r == "NS5":
        return A.Block(build_ast(ch[1]), sp)
    if r == "NS6":
        return A.Skip(sp)
    if r == "NV":
        return A.Var(ch[0].symbol, sp)
    if r == "NN":
        return A.Num(int(ch[0].symbol.replace("–", "-").replace("−", "-")), sp)
    if r in ("NA1", "NA2"):
        return build_ast(ch[0])
    if r in ("NA3", "NA4", "NA5"):
        op = {"NA3": "+", "NA4": "-", "NA5": "*"}[r]
        return A.BinA(op, build_ast(ch[0]), build_ast(ch[2]), sp)
    if r == "NA6":
        return A.ParenA(build_ast(ch[1]), sp)
    if r in ("NB1", "NB2"):
        return A.Cmp("=" if r == "NB1" else ">", build_ast(ch[0]), build_ast(ch[2]), sp)
    if r == "NB3":
        return A.Or(build_ast(ch[0]), build_ast(ch[2]), sp)
    if r == "NB4":
        return A.Not(build_ast(ch[1]), sp)
    if r == "NB5":
        return A.ParenB(build_ast(ch[1]), sp)
    raise ValueError(f"невідоме правило {r}")


def parse_tree(source: str) -> ParseNode:
    return _Parser(source).program().number()


def parse(source: str) -> ParseResult:
    tree = parse_tree(source)
    return ParseResult(source, tree, build_ast(tree))


def parse_program(source: str) -> A.Program:
    return parse(source).ast


def check(source: str) -> list[Diagnostic]:
    try:
        parse(source)
        return []
    except SiplSyntaxError as e:
        return [e.diagnostic]
