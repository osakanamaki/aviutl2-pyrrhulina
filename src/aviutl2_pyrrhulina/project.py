"""テスト用のプロジェクトファイル（.aup2）を組み立てる。

.aup2 は INI 形式のテキスト。項目名と値は、AviUtl2 で保存した .aup2 に
書かれているものをそのまま指定する（例: {"フレーム位置": "3", "診断表示": "0"}）。
省略した項目は AviUtl2 が既定値で補う。
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
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
        # 1 フレームだけのオブジェクトは 開始 == 終了（AviUtl2 では frame=0,0 と書く）。
        if self.start > self.end:
            raise ValueError(f"開始が終了より後になっています: {self.start},{self.end}")
        if self.midpoints and self.frames != sorted(set(self.frames)):
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


# 検証用プラグインが登録する、プレビューの描画結果を受け取るためのフィルタ。
PREVIEW_CAPTURE_EFFECT = "pyrrhulina capture"


@dataclass(frozen=True)
class PreviewTarget:
    """プレビューとして描画するときに、検証用プラグインへ渡す情報。"""

    # オブジェクト設定ウィンドウで選択するオブジェクトの位置（レイヤー番号とフレーム番号）。
    selected_layer: int
    selected_frame: int
    # 目印のオブジェクトのレイヤー番号。目印より上のレイヤーが重なったところで画像を受け取る。
    marker_layer: int


def add_preview_capture(project: Project, selected: TimelineObject) -> tuple[Project, PreviewTarget]:
    """プレビューの描画結果を受け取るためのオブジェクトを、project の一番下のレイヤーに足す。

    プレビューの画像を返す API が無いので、検証用プラグインのフィルタで受け取る。
    しくみは plugin/agent.cpp の冒頭の「プレビュー」を参照。
    - 目印: 一番下のレイヤーの次に置く小さな図形。受け取る画像には写らない。
    - フィルタオブジェクト: 目印の次に置く。上のレイヤーのオブジェクトごとにかかる。
    どちらも、シーンの最後より 1 フレーム長くする。同じフレームを続けて描かせるとき、
    検証用プラグインは隣のフレームを挟むので、隣のフレームが必ずあるようにするため。
    """
    if selected not in project.objects:
        raise ValueError("selected には、project.objects に含まれるオブジェクトを指定してください")
    marker_layer = max(timeline_object.layer for timeline_object in project.objects) + 1
    last_frame = max(timeline_object.end for timeline_object in project.objects) + 1
    marker = TimelineObject(
        marker_layer, 0, last_frame, [Effect("図形", {"サイズ": "1"}), Effect("標準描画")]
    )
    capture = TimelineObject(marker_layer + 1, 0, last_frame, [Effect(PREVIEW_CAPTURE_EFFECT)])
    captured_project = replace(project, objects=[*project.objects, marker, capture])
    return captured_project, PreviewTarget(selected.layer, selected.start, marker_layer)
