from pathlib import Path

import pytest
from PIL import Image

from aviutl2_pyrrhulina import EvidenceRecord, compare_images, write_report


def _save(path: Path, color: tuple[int, int, int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (4, 4), color).save(path)
    return path


def test_report_lists_failed_tests_first(tmp_path: Path) -> None:
    records = [
        EvidenceRecord("tests/test_a.py::test_passed", tmp_path / "a", outcome="passed"),
        EvidenceRecord("tests/test_b.py::test_failed", tmp_path / "b", outcome="failed", failure_text="boom"),
    ]

    text = write_report(tmp_path / "index.html", records).read_text(encoding="utf-8")

    assert text.index("test_failed") < text.index("test_passed")
    assert "boom" in text
    assert "失敗 1 件" in text


def test_report_refers_to_images_by_relative_path(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence" / "test_x"
    frame = _save(evidence_dir / "frame_00003.png", (1, 2, 3, 255))
    record = EvidenceRecord("test_x", evidence_dir, outcome="passed", frames={3: frame})

    text = write_report(tmp_path / "evidence" / "index.html", [record]).read_text(encoding="utf-8")

    assert 'src="test_x/frame_00003.png"' in text
    assert "フレーム 3" in text


def test_report_shows_baseline_actual_and_diff_side_by_side(tmp_path: Path) -> None:
    baseline = _save(tmp_path / "baselines" / "square.png", (1, 2, 3, 255))
    evidence_dir = tmp_path / "evidence" / "test_x"
    comparison = compare_images(Image.new("RGBA", (4, 4), (1, 2, 3, 255)), baseline, evidence_dir)
    record = EvidenceRecord("test_x", evidence_dir, outcome="passed", comparisons=[comparison])

    text = write_report(tmp_path / "evidence" / "index.html", [record]).read_text(encoding="utf-8")

    assert 'src="../baselines/square.png"' in text
    assert 'src="test_x/square.actual.png"' in text
    assert 'src="test_x/square.diff.png"' in text
    assert "一致" in text


def test_report_escapes_test_names(tmp_path: Path) -> None:
    record = EvidenceRecord("test_x[<b>]", tmp_path / "x", outcome="passed")

    text = write_report(tmp_path / "index.html", [record]).read_text(encoding="utf-8")

    assert "test_x[&lt;b&gt;]" in text
    assert "<b>" not in text


def test_report_does_not_load_external_files(tmp_path: Path) -> None:
    text = write_report(tmp_path / "index.html", [EvidenceRecord("t", tmp_path)]).read_text(encoding="utf-8")

    assert "http://" not in text and "https://" not in text


# AviUtl2 を起動せずに、fixture の記録と一覧の作成を確かめる。
_CONFTEST = """
import pytest
from aviutl2_pyrrhulina.environment import Environment

@pytest.fixture(scope="session")
def aviutl2_environment(tmp_path_factory):
    return Environment(tmp_path_factory.mktemp("app"))
"""

_TESTS = """
from pathlib import Path
from PIL import Image

BASELINE = Path(__file__).parent / "baselines" / "red.png"

def test_matches(aviutl2):
    aviutl2.assert_matches(Image.new("RGBA", (4, 4), (255, 0, 0, 255)), BASELINE)

def test_does_not_match(aviutl2):
    aviutl2.assert_matches(Image.new("RGBA", (4, 4), (0, 0, 255, 255)), BASELINE)

def test_without_aviutl2():
    pass
"""


def test_plugin_writes_report_after_session(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(test_sample=_TESTS)
    _save(pytester.path / "baselines" / "red.png", (255, 0, 0, 255))

    result = pytester.runpytest()

    result.assert_outcomes(passed=2, failed=1)
    report_path = pytester.path / ".aviutl2-pyrrhulina" / "evidence" / "index.html"
    result.stdout.fnmatch_lines([f"*{report_path}*"])
    text = report_path.read_text(encoding="utf-8")
    assert text.index("test_does_not_match") < text.index("test_matches")
    assert "test_without_aviutl2" not in text
    assert "不一致" in text and "一致" in text


def test_plugin_writes_no_report_without_aviutl2_tests(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_plain():\n    pass\n")

    pytester.runpytest().assert_outcomes(passed=1)

    assert not (pytester.path / ".aviutl2-pyrrhulina" / "evidence" / "index.html").exists()
