from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpan:
    start: int
    end: int
    line: int
    col: int
    end_line: int
    end_col: int

    def merge(self, other: SourceSpan) -> SourceSpan:
        first = self if self.start <= other.start else other
        last = self if self.end >= other.end else other
        return SourceSpan(first.start, last.end, first.line, first.col, last.end_line, last.end_col)

    def text(self, source: str) -> str:
        return source[self.start:self.end]

    def to_json(self) -> dict:
        return {"start": self.start, "end": self.end, "line": self.line, "col": self.col,
                "endLine": self.end_line, "endCol": self.end_col}


@dataclass
class Diagnostic:
    message: str
    span: SourceSpan | None = None
    hint: str | None = None

    def render(self, source: str | None = None, filename: str = "<input>") -> str:
        loc = f"{filename}:{self.span.line}:{self.span.col}" if self.span else filename
        out = [f"{loc}: помилка: {self.message}"]
        if self.span and source is not None:
            lines = source.splitlines() or [""]
            if 1 <= self.span.line <= len(lines):
                src_line = lines[self.span.line - 1]
                if self.span.end_line == self.span.line:
                    width = max(1, self.span.end_col - self.span.col)
                else:
                    width = max(1, len(src_line) - self.span.col + 1)
                out.append(f"  {self.span.line:>4} | {src_line}")
                out.append("       | " + " " * (self.span.col - 1) + "^" * width)
        if self.hint:
            out.append(f"  підказка: {self.hint}")
        return "\n".join(out)


class SiplError(Exception):
    def __init__(self, diagnostic: Diagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class SiplSyntaxError(SiplError):
    pass
