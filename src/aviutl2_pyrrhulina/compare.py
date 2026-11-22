"""描画結果を基準画像と比べる。"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PIL import Image, ImageChops


class ComparisonStatus(Enum):
    MATCHED = "一致"
    MISMATCHED = "不一致"
    MISSING_BASELINE = "基準画像なし"
    SIZE_MISMATCH = "サイズ違い"
    UPDATED = "基準画像を更新"


@dataclass(frozen=True)
class ImageComparison:
    """基準画像と比べた結果。証跡の一覧（index.html）にもこの内容を載せる。"""

    status: ComparisonStatus
    baseline_path: Path
    # 今回の画像。基準画像を更新したときは、基準画像そのものになる。
    actual_path: Path
    # 差分画像。大きさが同じ基準画像と比べたときだけ作る。
    diff_path: Path | None = None
    # 各画素・各チャンネルの差のうち最大のもの。比べられなかったときは None。
    max_difference: int | None = None
    tolerance: int = 0

    @property
    def passed(self) -> bool:
        return self.status in (ComparisonStatus.MATCHED, ComparisonStatus.UPDATED)

    def describe(self) -> str:
        if self.status == ComparisonStatus.MISSING_BASELINE:
            return f"基準画像がありません: {self.baseline_path}\n今回の画像: {self.actual_path}"
        if self.status == ComparisonStatus.SIZE_MISMATCH:
            return f"画像サイズが基準画像と違います: {self.baseline_path}\n今回の画像: {self.actual_path}"
        if self.status == ComparisonStatus.MISMATCHED:
            return (
                f"基準画像と一致しません（最大差 {self.max_difference} > 許容 {self.tolerance}）: "
                f"{self.baseline_path}\n今回の画像: {self.actual_path}\n差分: {self.diff_path}"
            )
        return f"{self.status.value}: {self.baseline_path}"


class ImageMismatch(AssertionError):
    def __init__(self, message: str, comparisons: list[ImageComparison] | None = None) -> None:
        super().__init__(message)
        self.comparisons = comparisons or []


def compare_images(
    actual: Image.Image,
    baseline_path: Path,
    evidence_dir: Path,
    *,
    tolerance: int = 0,
    update: bool = False,
) -> ImageComparison:
    """actual を基準画像と比べた結果を返す。一致しなくても例外にはしない。

    tolerance は、各画素・各チャンネルで許す差の最大値（0〜255）。
    完全に透明な画素は、色が違っていても同じとみなす。
    今回の画像と差分画像は、一致したときも evidence_dir に残す（目で確かめられるようにするため）。
    基準画像を書き換えるのは update=True のときだけ（人が見て承認した後に使う）。
    """
    if update:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        actual.save(baseline_path)
        return ImageComparison(ComparisonStatus.UPDATED, baseline_path, baseline_path, tolerance=tolerance)

    evidence_dir.mkdir(parents=True, exist_ok=True)
    actual_path = evidence_dir / f"{baseline_path.stem}.actual.png"
    actual.save(actual_path)
    if not baseline_path.exists():
        return ImageComparison(
            ComparisonStatus.MISSING_BASELINE, baseline_path, actual_path, tolerance=tolerance
        )

    baseline = Image.open(baseline_path).convert("RGBA")
    if baseline.size != actual.size:
        return ImageComparison(
            ComparisonStatus.SIZE_MISMATCH, baseline_path, actual_path, tolerance=tolerance
        )

    # チャンネルごとの差のうち最大のものを、画素ごとに 1 つの値にまとめる。
    bands = ImageChops.difference(_clear_invisible(actual), _clear_invisible(baseline)).split()
    difference = bands[0]
    for band in bands[1:]:
        difference = ImageChops.lighter(difference, band)
    max_difference = max(value for value, count in enumerate(difference.histogram()) if count)

    diff_path = evidence_dir / f"{baseline_path.stem}.diff.png"
    # 許容を超えた画素を白、それ以外を黒にする。差が小さくても見えるようにするため。
    difference.point(lambda value: 255 if value > tolerance else 0).save(diff_path)
    status = ComparisonStatus.MISMATCHED if max_difference > tolerance else ComparisonStatus.MATCHED
    return ImageComparison(status, baseline_path, actual_path, diff_path, max_difference, tolerance)


def assert_images_match(
    actual: Image.Image,
    baseline_path: Path,
    evidence_dir: Path,
    *,
    tolerance: int = 0,
    update: bool = False,
) -> ImageComparison:
    """actual が基準画像と一致することを確かめる。比べ方は compare_images と同じ。

    基準画像が無いとき、または一致しないときは ImageMismatch で失敗する。
    """
    comparison = compare_images(actual, baseline_path, evidence_dir, tolerance=tolerance, update=update)
    if not comparison.passed:
        raise ImageMismatch(comparison.describe(), [comparison])
    return comparison


def _clear_invisible(image: Image.Image) -> Image.Image:
    """完全に透明な画素の色を 0 にそろえる。見えない色の違いで失敗させないため。"""
    image = image.convert("RGBA")
    visible = image.getchannel("A").point(lambda alpha: 255 if alpha else 0)
    return Image.composite(image, Image.new("RGBA", image.size), visible)
