"""テストごとの証跡を記録し、まとめて目で確かめるための一覧（index.html）を作る。

一覧は 1 つの HTML ファイルで完結させる（外部の CSS・JavaScript・フォントは読み込まない）。
画像はコピーせず、index.html からの相対パスで参照する。
"""

import html
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote

from PIL import Image

from aviutl2_pyrrhulina.compare import ImageComparison
from aviutl2_pyrrhulina.thumbnail import save_animation, shrink

# 一覧で動きを見るためのアニメーションの大きさ（長い辺）。描画結果が大きくても一覧を軽く保つため。
ANIMATION_MAX_SIZE = 320
# 1 フレームの表示時間の範囲。フレームの間隔が空いていても、止まって見えたり速すぎたりしないようにする。
_MIN_FRAME_MS = 20
_MAX_FRAME_MS = 1000


def write_frames_animation(images: Mapping[int, Image.Image], project_fps: Fraction, path: Path) -> Path:
    """描画したフレームを、フレーム番号の間隔どおりの時間で再生するアニメーション WebP にする。

    例えば 0, 5, 10 フレームを描画したときは、5 フレーム分ずつ表示する。
    最後のフレームは、その前のフレームと同じ時間だけ表示する。
    """
    frames = sorted(images)
    if len(frames) < 2:
        raise ValueError("アニメーションには 2 フレーム以上が必要です")
    frame_ms = 1000 / project_fps
    durations = [(after - before) * frame_ms for before, after in zip(frames, frames[1:], strict=False)]
    durations.append(durations[-1])
    clamped = [round(min(max(duration, _MIN_FRAME_MS), _MAX_FRAME_MS)) for duration in durations]
    return save_animation([shrink(images[frame], ANIMATION_MAX_SIZE) for frame in frames], path, clamped)


@dataclass
class EvidenceRecord:
    """1 つのテストで残した証跡。"""

    test_id: str
    evidence_dir: Path
    # pytest の結果（"passed" / "failed" / "skipped"）。テストが終わってから入る。
    outcome: str = ""
    # 失敗したときの pytest の説明。
    failure_text: str = ""
    # 最後に描画したフレーム番号と、その PNG。
    frames: dict[int, Path] = field(default_factory=dict)
    # 最後に描画したフレームを動きとして見るためのアニメーション（2 フレーム以上のとき）。
    animation_path: Path | None = None
    comparisons: list[ImageComparison] = field(default_factory=list)

    @property
    def project_path(self) -> Path:
        return self.evidence_dir / "project.aup2"

    @property
    def log_path(self) -> Path:
        return self.evidence_dir / "aviutl2.log"


_OUTCOME_LABELS = {"failed": "失敗", "passed": "成功", "skipped": "スキップ"}

# 失敗したテストを先頭に出す。
_OUTCOME_ORDER = {"failed": 0, "": 1, "skipped": 2, "passed": 3}

_STYLE = """
body { font-family: sans-serif; margin: 16px; color: #222; background: #fff; }
h1 { font-size: 1.4em; }
section { border: 1px solid #ccc; border-radius: 6px; padding: 8px 12px; margin: 12px 0; }
section.failed { border-color: #c33; }
h2 { font-size: 1.05em; margin: 4px 0; word-break: break-all; }
.outcome { display: inline-block; padding: 0 8px; border-radius: 4px; color: #fff; margin-right: 8px; }
.outcome.failed { background: #c33; }
.outcome.passed { background: #393; }
.outcome.skipped, .outcome.unknown { background: #888; }
pre { background: #f6f6f6; padding: 8px; overflow-x: auto; white-space: pre-wrap; }
.row { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; }
figure { margin: 0; }
figcaption { font-size: 0.85em; color: #555; word-break: break-all; }
img { max-width: 100%; border: 1px solid #ccc; }
/* 透明な部分が分かるよう、背景を市松模様にする。 */
img.checker {
  background-color: #fff;
  background-image:
    linear-gradient(45deg, #ddd 25%, transparent 25%, transparent 75%, #ddd 75%),
    linear-gradient(45deg, #ddd 25%, transparent 25%, transparent 75%, #ddd 75%);
  background-size: 16px 16px;
  background-position: 0 0, 8px 8px;
}
.comparison { border-top: 1px dashed #ccc; padding-top: 6px; margin-top: 6px; }
.status-ng { color: #c33; font-weight: bold; }
.status-ok { color: #393; font-weight: bold; }
"""


def write_report(path: Path, records: Sequence[EvidenceRecord]) -> Path:
    """records の一覧を path（index.html）に書く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda record: (_OUTCOME_ORDER.get(record.outcome, 1), record.test_id))
    failed_count = sum(1 for record in records if record.outcome == "failed")
    sections = [_record_html(record, path.parent) for record in ordered]
    document = "\n".join(
        [
            "<!doctype html>",
            '<html lang="ja">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>ピルリナの証跡</title>",
            f"<style>{_STYLE}</style>",
            "</head>",
            "<body>",
            "<h1>ピルリナの証跡</h1>",
            f"<p>テスト {len(records)} 件（失敗 {failed_count} 件）。",
            "今回実行したテストだけを載せています。</p>",
            *sections,
            "</body>",
            "</html>",
        ]
    )
    path.write_text(document + "\n", encoding="utf-8")
    return path


def _record_html(record: EvidenceRecord, base_dir: Path) -> str:
    outcome_class = record.outcome if record.outcome in _OUTCOME_LABELS else "unknown"
    outcome_label = _OUTCOME_LABELS.get(record.outcome, "不明")
    parts = [
        f'<section class="{outcome_class}">',
        f'<h2><span class="outcome {outcome_class}">{outcome_label}</span>{_text(record.test_id)}</h2>',
    ]

    links = [
        _link(file_path, file_path.name, base_dir)
        for file_path in (record.project_path, record.log_path)
        if file_path.exists()
    ]
    if links:
        parts.append(f"<p>{' / '.join(links)}</p>")
    if record.failure_text:
        parts.append(f"<pre>{_text(record.failure_text)}</pre>")

    if record.frames:
        parts.append("<h3>描画したフレーム</h3>")
        figures = [
            _figure(image_path, f"フレーム {frame}", base_dir) for frame, image_path in record.frames.items()
        ]
        if record.animation_path is not None and record.animation_path.exists():
            figures.append(_figure(record.animation_path, "アニメーション", base_dir))
        parts.append(f'<div class="row">{"".join(figures)}</div>')

    if record.comparisons:
        parts.append("<h3>基準画像との比較</h3>")
        parts += [_comparison_html(comparison, base_dir) for comparison in record.comparisons]

    parts.append("</section>")
    return "\n".join(parts)


def _comparison_html(comparison: ImageComparison, base_dir: Path) -> str:
    status_class = "status-ok" if comparison.passed else "status-ng"
    summary = f'<span class="{status_class}">{_text(comparison.status.value)}</span>'
    if comparison.max_difference is not None:
        summary += f"（最大差 {comparison.max_difference} / 許容 {comparison.tolerance}）"
    figures = []
    if comparison.baseline_path.exists():
        figures.append(_figure(comparison.baseline_path, "基準画像", base_dir))
    if comparison.actual_path != comparison.baseline_path:
        figures.append(_figure(comparison.actual_path, "今回", base_dir))
    if comparison.diff_path is not None:
        figures.append(_figure(comparison.diff_path, "差分（白が許容を超えた画素）", base_dir))
    return "\n".join(
        [
            '<div class="comparison">',
            f"<p>{summary} {_text(str(comparison.baseline_path))}</p>",
            f'<div class="row">{"".join(figures)}</div>',
            "</div>",
        ]
    )


def _figure(image_path: Path, caption: str, base_dir: Path) -> str:
    url = _url(image_path, base_dir)
    return (
        f'<figure><a href="{url}"><img class="checker" src="{url}" alt="{_text(caption)}" loading="lazy"></a>'
        f"<figcaption>{_text(caption)}</figcaption></figure>"
    )


def _link(file_path: Path, label: str, base_dir: Path) -> str:
    return f'<a href="{_url(file_path, base_dir)}">{_text(label)}</a>'


def _url(file_path: Path, base_dir: Path) -> str:
    """index.html から file_path を参照する URL。"""
    try:
        relative = os.path.relpath(file_path.resolve(), base_dir.resolve())
    except ValueError:
        # ドライブが違うと相対パスにできないので、絶対パスの URL にする。
        return html.escape(file_path.resolve().as_uri())
    return html.escape(quote(Path(relative).as_posix()))


def _text(text: str) -> str:
    return html.escape(text)
