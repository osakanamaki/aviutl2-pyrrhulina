import pytest

from aviutl2_pyrrhulina import Effect, Project, TimelineObject


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
