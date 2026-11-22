import re
from pathlib import Path

from aviutl2_pyrrhulina.runner import MINIMUM_AVIUTL2_VERSION, _result_errors

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
