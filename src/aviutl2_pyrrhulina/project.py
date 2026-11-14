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
                f"frame={timeline_object.start},{timeline_object.end}",
            ]
            for effect_index, effect in enumerate(timeline_object.effects):
                lines += [f"[{object_index}.{effect_index}]", f"effect.name={effect.name}"]
                lines += [f"{key}={value}" for key, value in effect.params.items()]
        return "\n".join(lines) + "\n"

    def write(self, path: Path) -> None:
        path.write_text(self.to_text(), encoding="utf-8", newline="\r\n")
