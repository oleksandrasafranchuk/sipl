import json
import shutil

import pytest

from sipl.lexer import tokenize
from sipl.parser import parse
from sipl.visualization.parse_tree_view import render

GCD = "begin\n  while ¬M=N do\n    if M>N then M:=M–N else N:=N–M\nend"


def test_leaves_give_program_text():
    r = parse(GCD)
    assert r.tree.crown() == [t.text for t in tokenize(GCD) if t.kind != "EOF"]


def test_root_and_rules():
    t = parse(GCD).tree
    assert t.symbol == "<програма>" and t.rule == "NP1"
    assert [c.symbol for c in t.children] == ["begin", "<оператор>", "end"]
    assert t.children[1].rule == "NS4"


def test_mult_binds_tighter_in_tree():
    t = parse("begin R:=X+Y*Z end").tree
    expr = t.children[1].children[2]
    assert expr.rule == "NA3"
    assert expr.children[2].rule == "NA5"


def test_every_node_linked_to_source():
    for n in parse(GCD).tree.iter():
        frag = n.span.text(GCD)
        assert frag == n.symbol if n.terminal else frag.strip()


def test_text():
    txt = render(parse(GCD).tree, GCD, "text")
    assert "<програма> [NP1]" in txt and "└── end" in txt and "«M:=M–N»" in txt


def test_json():
    data = json.loads(render(parse(GCD).tree, GCD, "json"))
    root = data["root"]
    assert root["rule"] == "NP1" and root["text"] == GCD
    assert root["children"][1]["span"]["line"] == 2
    assert data["crown"][0] == "begin"


def test_dot():
    dot = render(parse(GCD).tree, GCD, "dot")
    assert dot.startswith("digraph") and "tooltip" in dot and "NS3" in dot


@pytest.mark.skipif(not shutil.which("dot"), reason="Graphviz не встановлено")
def test_svg():
    assert "<svg" in render(parse(GCD).tree, GCD, "svg")
