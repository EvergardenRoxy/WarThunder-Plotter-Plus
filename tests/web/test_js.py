import subprocess
from pathlib import Path


def test_node_tests_pass():
    root = Path(__file__).resolve().parents[2]
    files = sorted((root / "tests" / "js").glob("*.test.cjs"))
    assert files
    result = subprocess.run(
        ["node", "--test", *files], cwd=root, capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
