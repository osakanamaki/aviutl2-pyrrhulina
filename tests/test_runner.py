import re
from pathlib import Path

import pytest

from aviutl2_pyrrhulina.environment import Environment
from aviutl2_pyrrhulina.runner import (
    MAX_PATH_LENGTH,
    MINIMUM_AVIUTL2_VERSION,
    AviUtl2Error,
    _result_errors,
    render,
)

JOB_LINES = ["timeout\t55000", "project\tC:\\p.aup2", "render\t0\tC:\\f.rgba"]


def test_all_ok_has_no_errors() -> None:
    assert _result_errors(JOB_LINES, "ok\nok\nok\t320\t240\n") == []


def test_failed_command_is_reported_with_reason() -> None:
    errors = _result_errors(JOB_LINES, "ok\nok\nerror\trendering timeout\n")

    assert errors == ["render\t0\tC:\\f.rgba: rendering timeout"]


def test_empty_result_is_reported_instead_of_crashing() -> None:
    assert _result_errors(JOB_LINES, "") == ["プラグインの結果が 0 行で、命令の 3 行と合いません"]


def test_short_result_reports_both_failures_and_count() -> None:
    errors = _result_errors(JOB_LINES, "ok\nerror\tproject load timeout\n")

    assert errors == [
        "project\tC:\\p.aup2: project load timeout",
        "プラグインの結果が 2 行で、命令の 3 行と合いません",
    ]


def test_minimum_version_matches_plugin() -> None:
    # 検証用プラグインの RequiredVersion と、エラーで案内する本体のバージョンを合わせておく。
    source = (Path(__file__).parent.parent / "plugin" / "agent.cpp").read_text(encoding="utf-8")
    match = re.search(r"kRequiredVersion = (\d+);", source)
    assert match is not None
    required = int(match.group(1))
    major, minor, patch = (int(part) for part in MINIMUM_AVIUTL2_VERSION.split("."))

    assert required == major * 1000000 + minor * 10000 + patch * 100


# 作業フォルダの下で一番長いパスの部分（区切りの「\」を含む）。
RESULT_TEMP_NAME = "\\job.txt.result.tmp"


def _deep_dir(base: Path, length: int) -> Path:
    """base の下に、パスの長さがちょうど length 文字になるフォルダのパスを作る（フォルダは作らない）。"""
    path = base
    while len(str(path)) + 50 < length:
        path = path / ("d" * 40)
    return path / ("e" * (length - len(str(path)) - 1))


def test_too_long_work_dir_is_reported_before_launching(tmp_path: Path) -> None:
    # 区切りの「\」と job.txt.result.tmp を足すと、上限を 1 文字だけ超える長さ。
    work_dir = _deep_dir(tmp_path, MAX_PATH_LENGTH - len(RESULT_TEMP_NAME) + 1)
    environment = Environment(tmp_path / "no-such-app")  # 起動する前に止まるので、AviUtl2 は要らない

    with pytest.raises(AviUtl2Error, match="Windows の上限") as error:
        render(environment, tmp_path / "project.aup2", [0], work_dir)

    assert "job.txt.result.tmp" in str(error.value)
    assert "テスト名や parametrize の id を短く" in str(error.value)
    # 起動する前に止まるので、作業フォルダも作らない。
    assert not work_dir.exists()


def test_work_dir_just_within_limit_is_not_rejected_by_length(tmp_path: Path) -> None:
    work_dir = _deep_dir(tmp_path, MAX_PATH_LENGTH - len(RESULT_TEMP_NAME))
    environment = Environment(tmp_path / "no-such-app")

    # 長さの検査は通り、存在しない aviutl2.exe を起動しようとして失敗する。
    with pytest.raises(FileNotFoundError):
        render(environment, tmp_path / "project.aup2", [0], work_dir)
