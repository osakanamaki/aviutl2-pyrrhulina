"""assert_snapshot の振る舞いを、AviUtl2 を起動せずに別の pytest の実行で確かめる。"""

from pathlib import Path

import pytest
from PIL import Image

_CONFTEST = """
import pytest
from aviutl2_pyrrhulina.environment import Environment

@pytest.fixture(scope="session")
def aviutl2_environment(tmp_path_factory):
    return Environment(tmp_path_factory.mktemp("app"))
"""

# 描画の代わりに、色を指定した画像で RenderResult を作る。
_HELPERS = """

import pytest
from PIL import Image
from aviutl2_pyrrhulina import RenderResult

def result(*frames):
    color = (255, 0, 0, 255)
    return RenderResult({frame: Image.new("RGBA", (4, 4), color) for frame in frames}, "")
"""


def _baseline(pytester: pytest.Pytester, test_name: str, frame: int, name: str = "") -> Path:
    folder = pytester.path / "baselines" / "test_sample" / test_name
    return (folder / name if name else folder) / f"frame_{frame:05d}.png"


def _write_baseline(path: Path, red: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (4, 4), (red, 0, 0, 255)).save(path)


def _setup(pytester: pytest.Pytester, tests: str) -> None:
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(test_sample=_HELPERS + tests)


def test_missing_baselines_fail_and_update_writes_them(pytester: pytest.Pytester) -> None:
    _setup(pytester, "def test_draw(aviutl2):\n    aviutl2.assert_snapshot(result(0, 5))\n")

    pytester.runpytest().assert_outcomes(failed=1)
    assert not _baseline(pytester, "test_draw", 0).exists()

    pytester.runpytest("--aviutl2-update-baselines").assert_outcomes(passed=1)
    assert _baseline(pytester, "test_draw", 0).exists()
    assert _baseline(pytester, "test_draw", 5).exists()

    pytester.runpytest().assert_outcomes(passed=1)


def test_all_mismatched_frames_are_reported(pytester: pytest.Pytester) -> None:
    _setup(pytester, "def test_draw(aviutl2):\n    aviutl2.assert_snapshot(result(0, 5, 9))\n")
    _write_baseline(_baseline(pytester, "test_draw", 0), 255)
    _write_baseline(_baseline(pytester, "test_draw", 5), 10)
    _write_baseline(_baseline(pytester, "test_draw", 9), 20)

    result = pytester.runpytest()

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*3 フレーム中 2 フレームが基準画像と一致しません*"])
    assert "frame_00005.png" in result.stdout.str()
    assert "frame_00009.png" in result.stdout.str()


def test_tolerance_is_applied(pytester: pytest.Pytester) -> None:
    _setup(pytester, "def test_draw(aviutl2):\n    aviutl2.assert_snapshot(result(0), tolerance=3)\n")
    _write_baseline(_baseline(pytester, "test_draw", 0), 252)

    pytester.runpytest().assert_outcomes(passed=1)


def test_parametrized_tests_use_separate_baselines(pytester: pytest.Pytester) -> None:
    tests = (
        '@pytest.mark.parametrize("size", [1, 2])\n'
        "def test_draw(aviutl2, size):\n"
        "    aviutl2.assert_snapshot(result(0))\n"
    )
    _setup(pytester, tests)

    pytester.runpytest("--aviutl2-update-baselines").assert_outcomes(passed=2)

    assert _baseline(pytester, "test_draw_1_", 0).exists()
    assert _baseline(pytester, "test_draw_2_", 0).exists()


def test_named_snapshots_are_separated(pytester: pytest.Pytester) -> None:
    tests = (
        "def test_draw(aviutl2):\n"
        "    aviutl2.assert_snapshot(result(0))\n"
        '    aviutl2.assert_snapshot(result(0), name="after_move")\n'
    )
    _setup(pytester, tests)

    pytester.runpytest("--aviutl2-update-baselines").assert_outcomes(passed=1)

    assert _baseline(pytester, "test_draw", 0).exists()
    assert _baseline(pytester, "test_draw", 0, "after_move").exists()


def test_same_name_twice_is_an_error(pytester: pytest.Pytester) -> None:
    tests = (
        "def test_draw(aviutl2):\n"
        "    aviutl2.assert_snapshot(result(0))\n"
        "    aviutl2.assert_snapshot(result(0))\n"
    )
    _setup(pytester, tests)

    result = pytester.runpytest("--aviutl2-update-baselines")

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*ValueError*2 回呼ばれました*"])


def test_name_with_path_characters_is_an_error(pytester: pytest.Pytester) -> None:
    _setup(pytester, 'def test_draw(aviutl2):\n    aviutl2.assert_snapshot(result(0), name="../x")\n')

    result = pytester.runpytest("--aviutl2-update-baselines")

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*ValueError*使えない文字*"])


def test_baseline_folder_can_be_overridden(pytester: pytest.Pytester) -> None:
    conftest = _CONFTEST + (
        "\n@pytest.fixture\ndef aviutl2_baselines(request):\n"
        "    return request.config.rootpath / 'expected'\n"
    )
    pytester.makeconftest(conftest)
    pytester.makepyfile(
        test_sample=_HELPERS + "def test_draw(aviutl2):\n    aviutl2.assert_snapshot(result(0))\n"
    )

    pytester.runpytest("--aviutl2-update-baselines").assert_outcomes(passed=1)

    assert (pytester.path / "expected" / "test_sample" / "test_draw" / "frame_00000.png").exists()


def test_snapshot_comparisons_appear_in_report(pytester: pytest.Pytester) -> None:
    _setup(pytester, "def test_draw(aviutl2):\n    aviutl2.assert_snapshot(result(0))\n")
    _write_baseline(_baseline(pytester, "test_draw", 0), 10)

    pytester.runpytest().assert_outcomes(failed=1)

    text = (pytester.path / ".aviutl2-pyrrhulina" / "evidence" / "index.html").read_text(encoding="utf-8")
    assert "frame_00000.actual.png" in text
    assert "frame_00000.diff.png" in text
