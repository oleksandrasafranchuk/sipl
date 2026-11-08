from __future__ import annotations

import json
import shutil
import subprocess

from ..parse_tree import RULES, ParseNode

FORMATS = ("text", "json", "dot", "svg")


def fragment(node: ParseNode, source: str, limit: int = 38) -> str:
    text = " ".join(node.span.text(source).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def to_text(tree: ParseNode, source: str) -> str:
    lines: list[str] = []

    def label(n: ParseNode) -> str:
        if n.terminal:
            return n.symbol
        return f"{n.symbol} [{n.rule}]  {n.span.line}:{n.span.col}  «{fragment(n, source)}»"

    def walk(n: ParseNode, prefix: str, last: bool, root: bool):
        if root:
            lines.append(label(n))
            child_prefix = ""
        else:
            lines.append(prefix + ("└── " if last else "├── ") + label(n))
            child_prefix = prefix + ("    " if last else "│   ")
        for i, c in enumerate(n.children):
            walk(c, child_prefix, i == len(n.children) - 1, False)

    walk(tree, "", True, True)
    return "\n".join(lines)


def to_json(tree: ParseNode, source: str) -> str:
    data = {"crown": tree.crown(), "root": tree.to_json(source)}
    return json.dumps(data, ensure_ascii=False, indent=2)


def escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def to_dot(tree: ParseNode, source: str) -> str:
    out = ["digraph ParseTree {",
           '  graph [ordering=out, fontname="DejaVu Sans"];',
           '  node [fontname="DejaVu Sans", fontsize=11];',
           '  edge [arrowhead=none, color="#777777"];']
    for n in tree.iter():
        pos = f"{n.span.line}:{n.span.col}–{n.span.end_line}:{n.span.end_col}"
        tip = f"{pos}\n{n.span.text(source)}"
        if n.terminal:
            out.append(f'  n{n.id} [label="{escape(n.symbol)}", shape=box, style="rounded,filled", '
                       f'fillcolor="#fff4d6", color="#c9a227", tooltip="{escape(tip)}"];')
        else:
            tip = f"{n.rule}: {RULES[n.rule]}\n{tip}"
            out.append(f'  n{n.id} [label="{escape(n.symbol)}\\n{n.rule}", shape=ellipse, '
                       f'style=filled, fillcolor="#e3eefc", color="#4a78c2", tooltip="{escape(tip)}"];')
    for n in tree.iter():
        for c in n.children:
            out.append(f"  n{n.id} -> n{c.id};")
    out.append("}")
    return "\n".join(out)


def to_svg(tree: ParseNode, source: str) -> str:
    dot = shutil.which("dot")
    if not dot:
        raise RuntimeError("для формату svg потрібен Graphviz (команда dot)")
    res = subprocess.run([dot, "-Tsvg"], input=to_dot(tree, source).encode(),
                         capture_output=True, check=True)
    return res.stdout.decode()


def render(tree: ParseNode, source: str, fmt: str = "text") -> str:
    renderers = {"text": to_text, "json": to_json, "dot": to_dot, "svg": to_svg}
    return renderers[fmt](tree, source)
