"""テスト用のプロジェクトファイル（.aup2）を組み立てる。

.aup2 は INI 形式のテキスト。項目名と値は、AviUtl2 で保存した .aup2 に
書かれているものをそのまま指定する（例: {"フレーム位置": "3", "診断表示": "0"}）。
省略した項目は AviUtl2 が既定値で補う。
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Effect:
    name: str
    params: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TimelineObject:
    layer: int
    start: int
    end: int
    effects: Sequence[Effect]
    # 中間点のフレーム番号。指定したときは、移動するトラックバーの値を
    # 「開始, 各中間点, 終了」の順に並べる（例: 中間点 1 つなら "0.00,100.00,200.00,直線移動,0"）。
    midpoints: Sequence[int] = ()

    def __post_init__(self) -> None:
        if self.frames != sorted(set(self.frames)):
            raise ValueError(f"開始 < 中間点 < 終了 の順になっていません: {self.frames}")

    @property
    def frames(self) -> list[int]:
        return [self.start, *self.midpoints, self.end]


@dataclass(frozen=True)
class Project:
    width: int
    height: int
    objects: Sequence[TimelineObject]
    rate: int = 30
    scale: int = 1
    audio_rate: int = 44100
    # obj.getinfo("version") と同じ形式。既定は 2.1.17。
    version: int = 2011700

    def to_text(self) -> str:
        lines = [
            "[project]",
            f"version={self.version}",
            "[scene.0]",
            "scene=0",
            "name=Root",
            f"video.width={self.width}",
            f"video.height={self.height}",
            f"video.rate={self.rate}",
            f"video.scale={self.scale}",
            f"audio.rate={self.audio_rate}",
        ]
        for object_index, timeline_object in enumerate(self.objects):
            lines += [
                f"[{object_index}]",
                f"layer={timeline_object.layer}",
                "frame=" + ",".join(map(str, timeline_object.frames)),
            ]
            for effect_index, effect in enumerate(timeline_object.effects):
                lines += [f"[{object_index}.{effect_index}]", f"effect.name={effect.name}"]
                lines += [f"{key}={value}" for key, value in effect.params.items()]
        return "\n".join(lines) + "\n"

    def write(self, path: Path) -> None:
        path.write_text(self.to_text(), encoding="utf-8", newline="\r\n")
