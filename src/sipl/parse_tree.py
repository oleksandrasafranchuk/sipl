from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from .diagnostics import SourceSpan

NONTERMINALS = {
    "<програма>": "Prog", "<оператор>": "Stm", "<вираз>": "Aexp",
    "<умова>": "Bexp", "<змінна>": "Var", "<число>": "Num",
}

RULES = {
    "NP1": "<програма> ::= begin <оператор> end",
    "NS1": "<оператор> ::= <змінна> := <вираз>",
    "NS2": "<оператор> ::= <оператор> ; <оператор>",
    "NS3": "<оператор> ::= if <умова> then <оператор> else <оператор>",
    "NS4": "<оператор> ::= while <умова> do <оператор>",
    "NS5": "<оператор> ::= begin <оператор> end",
    "NS6": "<оператор> ::= skip",
    "NA1": "<вираз> ::= <число>",
    "NA2": "<вираз> ::= <змінна>",
    "NA3": "<вираз> ::= <вираз> + <вираз>",
    "NA4": "<вираз> ::= <вираз> – <вираз>",
    "NA5": "<вираз> ::= <вираз> * <вираз>",
    "NA6": "<вираз> ::= ( <вираз> )",
    "NB1": "<умова> ::= <вираз> = <вираз>",
    "NB2": "<умова> ::= <вираз> > <вираз>",
    "NB3": "<умова> ::= <умова> ∨ <умова>",
    "NB4": "<умова> ::= ¬ <умова>",
    "NB5": "<умова> ::= ( <умова> )",
    "NV": "<змінна> ::= … | M | N | …",
    "NN": "<число> ::= … | –1 | 0 | 1 | 2 | …",
}


@dataclass
class ParseNode:
    symbol: str
    span: SourceSpan
    rule: str | None = None
    children: list["ParseNode"] = field(default_factory=list)
    terminal: bool = False
    id: int = -1

    def iter(self) -> Iterator["ParseNode"]:
        yield self
        for c in self.children:
            yield from c.iter()

    def crown(self) -> list[str]:
        return [n.symbol for n in self.iter() if n.terminal]

    def number(self) -> "ParseNode":
        for i, node in enumerate(self.iter()):
            node.id = i
        return self

    def to_json(self, source: str | None = None) -> dict:
        d = {"id": self.id, "symbol": self.symbol,
             "kind": "terminal" if self.terminal else "nonterminal",
             "span": self.span.to_json()}
        if self.rule:
            d["rule"] = self.rule
            d["category"] = NONTERMINALS.get(self.symbol)
        if source is not None:
            d["text"] = self.span.text(source)
        if self.children:
            d["children"] = [c.to_json(source) for c in self.children]
        return d
