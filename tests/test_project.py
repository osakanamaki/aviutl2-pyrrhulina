import pytest

from aviutl2_pyrrhulina import Effect, PreviewTarget, Project, TimelineObject, add_preview_capture
from aviutl2_pyrrhulina.project import PREVIEW_CAPTURE_EFFECT


def test_to_text_numbers_objects_and_effects() -> None:
    project = Project(
        320,
        240,
        [
            TimelineObject(0, 0, 9, [Effect("図形", {"サイズ": 100}), Effect("標準描画")]),
            TimelineObject(2, 10, 19, [Effect("テキスト")]),
        ],
    )

    lines = project.to_text().splitlines()

    assert "video.width=320" in lines
    assert lines[lines.index("[0]") :] == [
        "[0]",
        "layer=0",
        "frame=0,9",
        "[0.0]",
        "effect.name=図形",
        "サイズ=100",
        "[0.1]",
        "effect.name=標準描画",
        "[1]",
        "layer=2",
        "frame=10,19",
        "[1.0]",
        "effect.name=テキスト",
    ]


def test_midpoints_are_written_between_start_and_end() -> None:
    project = Project(320, 240, [TimelineObject(0, 0, 20, [Effect("図形")], midpoints=[5, 10])])

    assert "frame=0,5,10,20" in project.to_text().splitlines()


@pytest.mark.parametrize("midpoints", [[0], [20], [10, 5], [5, 5], [25]])
def test_midpoints_out_of_order_are_rejected(midpoints: list[int]) -> None:
    with pytest.raises(ValueError, match="中間点"):
        TimelineObject(0, 0, 20, [Effect("図形")], midpoints=midpoints)


def test_one_frame_object_is_allowed() -> None:
    project = Project(320, 240, [TimelineObject(0, 5, 5, [Effect("図形")])])

    assert "frame=5,5" in project.to_text().splitlines()


def test_end_before_start_is_rejected() -> None:
    with pytest.raises(ValueError, match="開始が終了より後"):
        TimelineObject(0, 6, 5, [Effect("図形")])


def test_midpoint_in_one_frame_object_is_rejected() -> None:
    with pytest.raises(ValueError, match="中間点"):
        TimelineObject(0, 5, 5, [Effect("図形")], midpoints=[5])


def test_preview_capture_is_added_below_every_layer() -> None:
    square = TimelineObject(2, 0, 9, [Effect("square"), Effect("標準描画")])
    text = TimelineObject(0, 5, 20, [Effect("テキスト"), Effect("標準描画")])
    project = Project(320, 240, [square, text])

    captured, target = add_preview_capture(project, square)

    marker, capture = captured.objects[2:]
    assert captured.objects[:2] == [square, text]
    assert (marker.layer, capture.layer) == (3, 4)
    # 同じフレームを続けて描かせるとき、隣のフレームが必ずあるよう、最後より 1 フレーム長くする。
    assert (marker.start, marker.end) == (0, 21)
    assert (capture.start, capture.end) == (0, 21)
    assert [effect.name for effect in capture.effects] == [PREVIEW_CAPTURE_EFFECT]
    assert target == PreviewTarget(selected_layer=2, selected_frame=0, marker_layer=3)


def test_preview_capture_rejects_object_not_in_project() -> None:
    square = TimelineObject(0, 0, 9, [Effect("square"), Effect("標準描画")])
    other = TimelineObject(1, 0, 9, [Effect("square"), Effect("標準描画")])

    with pytest.raises(ValueError, match="project.objects"):
        add_preview_capture(Project(320, 240, [square]), other)
