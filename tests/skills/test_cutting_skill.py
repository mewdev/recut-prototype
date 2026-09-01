import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "skills" / "cutting" / "scripts" / "check_skill.py"
_spec = importlib.util.spec_from_file_location("cutting_check_skill", _SCRIPT)
_check_skill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_check_skill)


def test_cutting_skill_docs_match_live_code():
    issues = _check_skill.run()
    assert not issues, "\n".join(issues)
