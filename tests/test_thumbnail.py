from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image, ImageSequence

from aviutl2_pyrrhulina import Project, RenderResult, ThumbnailSizeWarning, make_thumbnail, thumbnail
from aviutl2_pyrrhulina.environment import Environment
from aviutl2_pyrrhulina.evidence import write_frames_animation
from aviutl2_pyrrhulina.thumbnail import fit_to_square, read_frame_rate, save_animation, thumbnail_frames


def test_frames_are_thinned_out_evenly() -> None:
    assert thumbnail_frames(Fraction(60), seconds=0.1, fps=30) == [0, 2, 4]
    assert thumbnail_frames(Fraction(30), seconds=0.2, fps=15, start=10) == [10, 12, 14]


def test_default_length_is_three_seconds_at_30fps() -> None:
    assert len(thumbnail_frames(Fraction(30), seconds=3, fps=30)) == 90


@pytest.mark.parametrize("seconds", [0, 10.5])
def test_length_out_of_range_is_an_error(seconds: float) -> None:
    with pytest.raises(ValueError, match="長さ"):
        thumbnail_frames(Fraction(30), seconds=seconds, fps=30)


def test_ten_seconds_is_allowed() -> None:
    assert len(thumbnail_frames(Fraction(30), seconds=10, fps=30)) == 300


def test_fps_that_does_not_divide_project_rate_is_an_error() -> None:
    with pytest.raises(ValueError, match="割り切れません"):
        thumbnail_frames(Fraction(30), seconds=1, fps=20)


def test_fps_higher_than_project_rate_is_an_error() -> None:
    with pytest.raises(ValueError, match="割り切れません"):
        thumbnail_frames(Fraction(30), seconds=1, fps=60)


def test_frame_is_fitted_to_square_keeping_aspect_ratio() -> None:
    image = Image.new("RGBA", (400, 200), (255, 0, 0, 255))

    fitted = fit_to_square(image, 206)

    assert fitted.size == (206, 206)
    # 横長なので、上下に透明な余白ができる。
    assert fitted.getbbox() == (0, 51, 206, 154)


def test_background_fills_margin() -> None:
    fitted = fit_to_square(Image.new("RGBA", (400, 200), (255, 0, 0, 255)), 206, (0, 0, 255))

    assert fitted.getpixel((0, 0)) == (0, 0, 255, 255)


@pytest.mark.parametrize("suffix", [".webp", ".gif"])
def test_animation_is_saved(tmp_path: Path, suffix: str) -> None:
    images = [Image.new("RGBA", (8, 8), (value, 0, 0, 255)) for value in (0, 128, 255)]

    path = save_animation(images, tmp_path / f"anim{suffix}", [100, 100, 100])

    with Image.open(path) as saved:
        assert len(_durations(saved)) == 3
        assert saved.info["loop"] == 0


def test_unknown_suffix_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=".webp か .gif"):
        save_animation([Image.new("RGBA", (8, 8))], tmp_path / "anim.png", [100])


def test_frame_rate_is_read_from_project_file(tmp_path: Path) -> None:
    path = tmp_path / "project.aup2"
    Project(320, 240, [], rate=60000, scale=1001).write(path)

    assert read_frame_rate(path) == Fraction(60000, 1001)


def _fake_render(color: tuple[int, int, int, int]):  # noqa: ANN202
    def render(environment, project_path, frames, work_dir, timeout):  # noqa: ANN001, ANN202
        return RenderResult({frame: Image.new("RGBA", (64, 64), color) for frame in frames}, "")

    return render


def test_thumbnail_is_made_from_rendered_frames(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(thumbnail, "render", _fake_render((255, 0, 0, 255)))

    path = make_thumbnail(
        Environment(tmp_path / "app"), Project(320, 240, []), tmp_path / "thumb.webp", seconds=1, fps=15
    )

    with Image.open(path) as saved:
        assert saved.size == (206, 206)
        # 同じ絵が続くフレームは、Pillow が 1 つにまとめて表示時間を足す。
        assert sum(_durations(saved)) in (1000, 1005)


def test_large_thumbnail_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(thumbnail, "render", _fake_render((255, 0, 0, 255)))
    monkeypatch.setattr(thumbnail, "WARNING_BYTES", 1)

    with pytest.warns(ThumbnailSizeWarning, match="MB"):
        make_thumbnail(
            Environment(tmp_path / "app"), Project(320, 240, []), tmp_path / "thumb.gif", seconds=1
        )


def test_frames_animation_follows_frame_gaps(tmp_path: Path) -> None:
    images = {frame: Image.new("RGBA", (8, 8), (frame * 20, 0, 0, 255)) for frame in (0, 3, 9)}

    path = write_frames_animation(images, Fraction(30), tmp_path / "frames.webp")

    with Image.open(path) as saved:
        assert _durations(saved) == [100, 200, 200]


def _durations(image: Image.Image) -> list[int]:
    """各フレームの表示時間。WebP は読み込むまで表示時間が入らない。"""
    durations = []
    for frame in ImageSequence.Iterator(image):
        frame.load()
        durations.append(frame.info["duration"])
    return durations
