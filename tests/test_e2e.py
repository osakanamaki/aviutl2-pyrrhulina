from pathlib import Path

import pytest

from aviutl2_pyrrhulina import AviUtl2Error, Effect, Project, TimelineObject
from aviutl2_pyrrhulina.pytest_plugin import AviUtl2

BASELINES = Path(__file__).parent / "baselines"


def _project(script: str, params: dict[str, object] | None = None) -> Project:
    return Project(320, 240, [TimelineObject(0, 0, 9, [Effect(script, params or {}), Effect("標準描画")])])


def test_script_draws_with_given_parameter(aviutl2: AviUtl2) -> None:
    result = aviutl2.render(_project("square", {"サイズ": "100.00"}), [0, 9])

    # 100×100 の四角形が中央に描かれる。
    # 色は R・G・B がすべて違う値にしてある。チャンネルの取り違えを見つけるため。
    assert result.images[0].getbbox() == (110, 70, 210, 170)
    assert result.images[0].getpixel((160, 120)) == (0x28, 0x8C, 0xD2, 255)
    assert result.images[0].getpixel((0, 0)) == (0, 0, 0, 0)
    assert result.log_lines("[SCRIPT] [square] size=100")
    aviutl2.assert_matches(result.images[9], BASELINES / "square_100.png")


def test_script_error_is_reported(aviutl2: AviUtl2) -> None:
    with pytest.raises(AviUtl2Error, match="script exception"):
        aviutl2.render(_project("broken"), [0])


def test_frame_out_of_range_is_reported(aviutl2: AviUtl2) -> None:
    with pytest.raises(AviUtl2Error, match="rendering_scene_video failed"):
        aviutl2.render(_project("square"), [1000])


def test_endless_script_reports_the_step_that_timed_out(aviutl2: AviUtl2) -> None:
    with pytest.raises(AviUtl2Error) as error:
        aviutl2.render(_project("endless"), [0, 1], timeout=6)

    assert "render\t0\t" in str(error.value) and "rendering timeout" in str(error.value)
    assert "skipped because the time limit was reached" in str(error.value)


def test_track_value_follows_midpoints(aviutl2: AviUtl2) -> None:
    square = Effect("square", {"サイズ": "20.00,100.00,60.00,直線移動,0"})
    project = Project(320, 240, [TimelineObject(0, 0, 20, [square, Effect("標準描画")], midpoints=[10])])

    result = aviutl2.render(project, [0, 5, 10, 15, 20])

    # 四角形は画面（320×240）の中央に描かれるので、描画範囲から大きさが分かる。
    expected_sizes = {0: 20, 5: 60, 10: 100, 15: 80, 20: 60}
    for frame, size in expected_sizes.items():
        left, top = 160 - size // 2, 120 - size // 2
        assert result.images[frame].getbbox() == (left, top, left + size, top + size), f"frame {frame}"


def test_known_log_error_can_be_ignored(aviutl2: AviUtl2) -> None:
    with pytest.raises(AviUtl2Error, match="canLoadFile"):
        aviutl2.render(_project("missing_image"), [0])

    aviutl2.render(_project("missing_image"), [0], ignore_log_errors=["ImageService::canLoadFile"])


def test_ignoring_one_error_does_not_hide_others(aviutl2: AviUtl2) -> None:
    with pytest.raises(AviUtl2Error, match="script exception"):
        aviutl2.render(_project("broken"), [0], ignore_log_errors=["ImageService::canLoadFile"])
