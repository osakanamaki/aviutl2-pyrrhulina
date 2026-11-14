"""描画結果を基準画像と比べる。"""

from pathlib import Path

from PIL import Image, ImageChops


class ImageMismatch(AssertionError):
    pass


def assert_images_match(
    actual: Image.Image,
    baseline_path: Path,
    evidence_dir: Path,
    *,
    tolerance: int = 0,
    update: bool = False,
) -> None:
    """actual が基準画像と一致することを確かめる。

    tolerance は、各画素・各チャンネルで許す差の最大値（0〜255）。
    完全に透明な画素は、色が違っていても同じとみなす。
    基準画像が無いとき、または一致しないときは、実際の画像を evidence_dir に残して失敗する。
    基準画像を書き換えるのは update=True のときだけ（人が見て承認した後に使う）。
    """
    if update:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        actual.save(baseline_path)
        return

    evidence_dir.mkdir(parents=True, exist_ok=True)
    actual_path = evidence_dir / f"{baseline_path.stem}.actual.png"
    if not baseline_path.exists():
        actual.save(actual_path)
        raise ImageMismatch(f"基準画像がありません: {baseline_path}\n今回の画像: {actual_path}")

    baseline = Image.open(baseline_path).convert("RGBA")
    if baseline.size != actual.size:
        actual.save(actual_path)
        raise ImageMismatch(
            f"画像サイズが違います: 基準 {baseline.size} / 今回 {actual.size}\n今回の画像: {actual_path}"
        )

    # チャンネルごとの差のうち最大のものを、画素ごとに 1 つの値にまとめる。
    bands = ImageChops.difference(_clear_invisible(actual), _clear_invisible(baseline)).split()
    difference = bands[0]
    for band in bands[1:]:
        difference = ImageChops.lighter(difference, band)
    max_difference = max(value for value, count in enumerate(difference.histogram()) if count)
    if max_difference > tolerance:
        actual.save(actual_path)
        diff_path = evidence_dir / f"{baseline_path.stem}.diff.png"
        # 許容を超えた画素を白、それ以外を黒にする。差が小さくても見えるようにするため。
        difference.point(lambda value: 255 if value > tolerance else 0).save(diff_path)
        raise ImageMismatch(
            f"基準画像と一致しません（最大差 {max_difference} > 許容 {tolerance}）: {baseline_path}\n"
            f"今回の画像: {actual_path}\n差分: {diff_path}"
        )


def _clear_invisible(image: Image.Image) -> Image.Image:
    """完全に透明な画素の色を 0 にそろえる。見えない色の違いで失敗させないため。"""
    image = image.convert("RGBA")
    visible = image.getchannel("A").point(lambda alpha: 255 if alpha else 0)
    return Image.composite(image, Image.new("RGBA", image.size), visible)
