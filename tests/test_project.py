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
