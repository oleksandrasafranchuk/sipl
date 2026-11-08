from conftest import EXAMPLES

from sipl.cli import main


def ex(name):
    return str(EXAMPLES / name)


def test_check(tmp_path, capsys):
    assert main(["check", ex("gcd.sipl")]) == 0
    bad = tmp_path / "bad.sipl"
    bad.write_text("begin X:=1; end", encoding="utf-8")
    assert main(["check", str(bad)]) == 1
    assert "bad.sipl:1:13" in capsys.readouterr().err


def test_parse_and_term(capsys):
    assert main(["parse", ex("gcd.sipl")]) == 0
    assert capsys.readouterr().out.startswith("Program")
    assert main(["term", ex("gcd.sipl")]) == 0
    assert capsys.readouterr().out.startswith("WH(")


def test_tree(tmp_path):
    for fmt in ("text", "json", "dot"):
        out = tmp_path / f"t.{fmt}"
        assert main(["tree", ex("gcd.sipl"), "-f", fmt, "-o", str(out)]) == 0
        assert out.stat().st_size > 100


def test_eval_exit_codes(capsys):
    assert main(["eval", ex("gcd.sipl"), "-s", "M=8, N=16", "--trace"]) == 0
    out = capsys.readouterr().out
    assert "AF_WH" in out and "[M↦8, N↦8]" in out
    assert main(["eval", ex("gcd.sipl"), "-s", "M=0, N=3"]) == 3
    assert main(["eval", ex("gcd.sipl"), "-s", "M=1, N=-1", "--max-steps", "300"]) == 4


def test_prove_exit_codes(capsys):
    assert main(["prove", ex("factorial.sipl"), ex("factorial.spec")]) == 0
    assert "не спростовано" in capsys.readouterr().out
    assert main(["prove", ex("gcd.sipl"), ex("gcd_wrong.spec")]) == 5
