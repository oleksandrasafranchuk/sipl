from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from . import ast as A
from .diagnostics import SiplError
from .parser import parse
from .semantics import terms as T
from .semantics.builder import sem_P
from .semantics.evaluator import evaluate
from .semantics.state import parse_state
from .visualization.parse_tree_view import FORMATS, render

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_UNDEFINED = 3
EXIT_UNKNOWN = 4
EXIT_REFUTED = 5


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def output(text: str, path: str | None):
    if path:
        Path(path).write_text(text + "\n", encoding="utf-8")
        print(f"записано: {path}", file=sys.stderr)
    else:
        print(text)


def ast_text(node, prefix: str = "", last: bool = True, root: bool = True) -> list[str]:
    label = type(node).__name__
    if isinstance(node, A.Num):
        label += f" {node.value}"
    elif isinstance(node, A.Var):
        label += f" {node.name}"
    elif isinstance(node, (A.BinA, A.Cmp)):
        label += f" '{node.op}'"
    if node.span:
        label += f"   {node.span.line}:{node.span.col}"
    lines = [label if root else prefix + ("└─ " if last else "├─ ") + label]
    sub = "" if root else prefix + ("   " if last else "│  ")
    kids = A.children(node)
    for i, c in enumerate(kids):
        lines += ast_text(c, sub, i == len(kids) - 1, False)
    return lines


def cmd_check(a) -> int:
    parse(read(a.file))
    print(f"{a.file}: програма синтаксично правильна")
    return EXIT_OK


def cmd_parse(a) -> int:
    output("\n".join(ast_text(parse(read(a.file)).ast)), a.output)
    return EXIT_OK


def cmd_tree(a) -> int:
    src = read(a.file)
    output(render(parse(src).tree, src, a.format), a.output)
    return EXIT_OK


def cmd_term(a) -> int:
    output(T.render(sem_P(parse(read(a.file)).ast)), a.output)
    return EXIT_OK


def cmd_eval(a) -> int:
    term = sem_P(parse(read(a.file)).ast)
    state = parse_state(a.state)
    res = evaluate(term, state, max_steps=a.max_steps, trace=a.trace)
    lines = [e.render() for e in res.trace]
    if lines:
        lines.append("")
    lines.append(res.summary())
    output("\n".join(lines), a.output)
    return {True: EXIT_OK, False: EXIT_UNDEFINED, None: EXIT_UNKNOWN}[res.defined]


def cmd_prove(a) -> int:
    from .proof.assistant import parse_proof_spec, prove, render_report
    spec = parse_proof_spec(read(a.spec))
    rep = prove(parse(read(a.file)).ast, spec)
    output(render_report(rep, spec), a.output)
    return EXIT_OK if rep.partial and rep.total is not False else EXIT_REFUTED


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sipl", description="Інструменти мови SIPL")
    p.add_argument("--version", action="version", version=f"sipl {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="КОМАНДА")

    def add(name, func, help_):
        sp = sub.add_parser(name, help=help_, description=help_)
        sp.add_argument("file", help="файл програми .sipl")
        sp.add_argument("-o", "--output", help="записати результат у файл")
        sp.set_defaults(func=func)
        return sp

    add("check", cmd_check, "перевірити синтаксис програми")
    add("parse", cmd_parse, "показати AST")
    sp = add("tree", cmd_tree, "дерево синтаксичного виводу")
    sp.add_argument("-f", "--format", choices=FORMATS, default="text")
    add("term", cmd_term, "семантичний терм програми")
    sp = add("eval", cmd_eval, "обчислити програму на стані")
    sp.add_argument("-s", "--state", required=True, help='стан, наприклад "M=8, N=16"')
    sp.add_argument("--trace", action="store_true", help="показати застосовані правила")
    sp.add_argument("--max-steps", type=int, default=200_000, help="ліміт кроків обчислення")
    sp = add("prove", cmd_prove, "перевірити коректність програми")
    sp.add_argument("spec", help="файл специфікації .spec")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SiplError as e:
        try:
            src = read(args.file)
        except OSError:
            src = None
        print(e.diagnostic.render(src, args.file), file=sys.stderr)
        return EXIT_ERROR
    except (OSError, RuntimeError) as e:
        print(f"помилка: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
