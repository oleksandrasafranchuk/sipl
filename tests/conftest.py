import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
EXAMPLES = ROOT / "examples"
GOLDEN = Path(__file__).resolve().parent / "golden"
