from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import Diagnostic, SiplSyntaxError, SourceSpan

KEYWORDS = {"begin", "end", "if", "then", "else", "while", "do", "skip"}
EXT_KEYWORDS = {"true", "false"}

BASE_OPS = [
    (":=", ":="), ("\\/", "OR"), (";", ";"), ("+", "+"), ("-", "-"), ("–", "-"),
    ("−", "-"), ("*", "*"), ("∗", "*"), ("(", "("), (")", ")"), ("=", "="),
    (">", ">"), ("¬", "NOT"), ("!", "NOT"), ("∨", "OR"), ("|", "OR"),
]
EXT_OPS = [
    ("->", "IMPL"), ("=>", "IMPL"), (">=", ">="), ("<=", "<="), ("!=", "!="),
    ("/\\", "AND"), ("⇒", "IMPL"), ("→", "IMPL"), ("≥", ">="), ("≤", "<="),
    ("≠", "!="), ("<", "<"), ("∧", "AND"), ("&", "AND"), ("/", "/"), ("%", "%"),
    (",", ","),
]
WORD_OPS = {"not": "NOT", "or": "OR"}
EXT_WORD_OPS = {"and": "AND"}

OP_DISPLAY = {"OR": "∨", "NOT": "¬", "AND": "∧", "IMPL": "⇒"}


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    text: str
    span: SourceSpan

    def describe(self) -> str:
        if self.kind == "EOF":
            return "кінець тексту"
        return f"«{self.text}»"


def tokenize(source: str, extended: bool = False) -> list[Token]:
    ops = sorted(BASE_OPS + (EXT_OPS if extended else []), key=lambda p: -len(p[0]))
    words = dict(WORD_OPS, **(EXT_WORD_OPS if extended else {}))
    tokens: list[Token] = []
    i, line, col = 0, 1, 1
    n = len(source)

    def span(start: int, end: int, l0: int, c0: int) -> SourceSpan:
        return SourceSpan(start, end, l0, c0, l0, c0 + (end - start))

    while i < n:
        ch = source[i]
        if ch == "\n":
            i, line, col = i + 1, line + 1, 1
            continue
        if ch.isspace():
            i, col = i + 1, col + 1
            continue
        if source.startswith("//", i):
            while i < n and source[i] != "\n":
                i += 1
            continue
        start, l0, c0 = i, line, col
        if ch.isdigit():
            while i < n and source[i].isdigit():
                i += 1
            if i < n and (source[i].isalpha() or source[i] == "_"):
                j = i
                while j < n and (source[j].isalnum() or source[j] == "_"):
                    j += 1
                raise SiplSyntaxError(Diagnostic(
                    f"некоректна лексема «{source[start:j]}»: ім'я змінної не може починатися з цифри",
                    span(start, j, l0, c0)))
            text = source[start:i]
            tokens.append(Token("NUM", text, text, span(start, i, l0, c0)))
            col += i - start
            continue
        if ch.isalpha() or ch == "_":
            while i < n and (source[i].isalnum() or source[i] == "_"):
                i += 1
            text = source[start:i]
            sp = span(start, i, l0, c0)
            col += i - start
            if text in KEYWORDS or (extended and text in EXT_KEYWORDS):
                tokens.append(Token("KW", text, text, sp))
            elif text in words:
                tokens.append(Token("OP", words[text], text, sp))
            else:
                tokens.append(Token("IDENT", text, text, sp))
            continue
        for text, value in ops:
            if source.startswith(text, i):
                i += len(text)
                col += len(text)
                tokens.append(Token("OP", value, text, span(start, i, l0, c0)))
                break
        else:
            hint = None
            if ch in "<≤≥≠&∧":
                hint = ("у SIPL є лише порівняння = та >; "
                        "наприклад, a<b записується як b>a, a≠b — як ¬a=b")
            elif ch == ":":
                hint = "присвоєння записується як «:=»"
            raise SiplSyntaxError(Diagnostic(
                f"невідомий символ «{ch}»", span(i, i + 1, l0, c0), hint=hint))
    eof = SourceSpan(n, n, line, col, line, col)
    tokens.append(Token("EOF", "", "", eof))
    return tokens
