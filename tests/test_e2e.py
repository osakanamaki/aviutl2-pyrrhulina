import os
import subprocess
from pathlib import Path

import pytest

from aviutl2_pyrrhulina import AviUtl2Error, Effect, Project, TimelineObject
from aviutl2_pyrrhulina.environment import Environment
from aviutl2_pyrrhulina.pytest_plugin import AviUtl2
from aviutl2_pyrrhulina.runner import JOB_ENV_VAR

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


def test_image_is_not_flipped(aviutl2: AviUtl2) -> None:
    result = aviutl2.render(_project("corner"), [0])

    # 中央（160, 120）から左に 100、上に 80 ずれた、40×40 の四角形。
    assert result.images[0].getbbox() == (40, 20, 80, 60)


def test_one_frame_object_can_be_rendered(aviutl2: AviUtl2) -> None:
    square = TimelineObject(0, 0, 0, [Effect("square", {"サイズ": "100.00"}), Effect("標準描画")])

    result = aviutl2.render(Project(320, 240, [square]), [0])

    assert result.images[0].getbbox() == (110, 70, 210, 170)


# aviutl2 fixture を使わないので、マーカーは自動では付かない。
@pytest.mark.aviutl2
def test_plugin_reports_exception_instead_of_crashing(
    aviutl2_environment: Environment, tmp_path: Path
) -> None:
    # Python 側の render() は正しい命令しか作らないので、ジョブファイルを直接書く。
    project_path = tmp_path / "project.aup2"
    _project("square").write(project_path)
    job_path = tmp_path / "job.txt"
    job_path.write_text(
        f"timeout\t20000\nproject\t{project_path}\nrender\tnot-a-number\t{tmp_path / 'frame.rgba'}\n",
        encoding="utf-8",
    )

    process = subprocess.run(
        [str(aviutl2_environment.exe), str(project_path)],
        cwd=aviutl2_environment.root,
        env={**os.environ, JOB_ENV_VAR: str(job_path)},
        timeout=60,
    )

    results = Path(f"{job_path}.result").read_text(encoding="utf-8").splitlines()
    assert results[:2] == ["ok", "ok"]
    assert results[2].startswith("error\texception: ")
    assert process.returncode == 0


def test_snapshot_compares_every_frame(aviutl2: AviUtl2) -> None:
    square = Effect("square", {"サイズ": "20.00,100.00,直線移動,0"})
    project = Project(320, 240, [TimelineObject(0, 0, 10, [square, Effect("標準描画")])])

    result = aviutl2.render(project, [0, 5, 10])

    aviutl2.assert_snapshot(result)
