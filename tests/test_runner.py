from aviutl2_pyrrhulina.runner import _result_errors

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
