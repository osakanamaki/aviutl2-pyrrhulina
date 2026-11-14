from pathlib import Path

import pytest
from PIL import Image

from aviutl2_pyrrhulina import ImageMismatch, assert_images_match


def _image(color: tuple[int, int, int, int]) -> Image.Image:
    return Image.new("RGBA", (4, 4), color)


def test_same_image_matches(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.png"
    _image((10, 20, 30, 255)).save(baseline)

    assert_images_match(_image((10, 20, 30, 255)), baseline, tmp_path / "evidence")


def test_difference_within_tolerance_matches(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.png"
    _image((10, 20, 30, 255)).save(baseline)

    assert_images_match(_image((12, 20, 30, 255)), baseline, tmp_path / "evidence", tolerance=2)


def test_mismatch_leaves_actual_and_diff(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.png"
    _image((10, 20, 30, 255)).save(baseline)

    with pytest.raises(ImageMismatch):
        assert_images_match(_image((13, 20, 30, 255)), baseline, tmp_path / "evidence", tolerance=2)

    assert (tmp_path / "evidence" / "baseline.actual.png").exists()
    assert (tmp_path / "evidence" / "baseline.diff.png").exists()


def test_missing_baseline_fails_without_creating_it(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.png"

    with pytest.raises(ImageMismatch):
        assert_images_match(_image((0, 0, 0, 255)), baseline, tmp_path / "evidence")

    assert not baseline.exists()
    assert (tmp_path / "evidence" / "baseline.actual.png").exists()


def test_size_mismatch_fails(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.png"
    Image.new("RGBA", (8, 4)).save(baseline)

    with pytest.raises(ImageMismatch):
        assert_images_match(_image((0, 0, 0, 0)), baseline, tmp_path / "evidence")


def test_update_writes_baseline(tmp_path: Path) -> None:
    baseline = tmp_path / "new" / "baseline.png"

    assert_images_match(_image((1, 2, 3, 255)), baseline, tmp_path / "evidence", update=True)

    assert Image.open(baseline).getpixel((0, 0)) == (1, 2, 3, 255)


def test_color_of_fully_transparent_pixels_is_ignored(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.png"
    _image((0, 0, 0, 0)).save(baseline)

    assert_images_match(_image((255, 255, 255, 0)), baseline, tmp_path / "evidence")
