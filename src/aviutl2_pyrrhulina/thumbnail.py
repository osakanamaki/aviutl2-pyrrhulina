"""描画結果から、AviUtl2 Catalog 用の動くサムネイル（アニメーション WebP / GIF）を作る。

テストではないので pytest を使わずに呼べる。コマンドとしても使える:

    aviutl2-pyrrhulina-thumbnail project.aup2 thumbnail.webp --script my-script=script
"""

import argparse
import os
import re
import warnings
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageColor

from aviutl2_pyrrhulina.environment import DEFAULT_APP_DIR, Environment, create_environment
from aviutl2_pyrrhulina.project import Project
from aviutl2_pyrrhulina.runner import render

# カタログの公式ガイドの推奨は 1:1、206×206px。
THUMBNAIL_SIZE = 206
DEFAULT_SECONDS = 3.0
MAX_SECONDS = 10.0
DEFAULT_FPS = 30
# カタログ側に上限は無いが、大きすぎると表示が重くなるので警告する。
WARNING_BYTES = 10 * 1024 * 1024

_FORMATS = {".webp": "WEBP", ".gif": "GIF"}

# 描画の制限時間。フレーム数が多いと時間がかかるので、フレーム数に応じて延ばす。
_TIMEOUT_BASE_SECONDS = 60
_TIMEOUT_PER_FRAME_SECONDS = 0.5

Color = tuple[int, int, int] | tuple[int, int, int, int]


class ThumbnailSizeWarning(UserWarning):
    pass


def thumbnail_frames(project_fps: Fraction, seconds: float, fps: int, start: int = 0) -> list[int]:
    """サムネイルに使うフレーム番号。

    プロジェクトのフレームを一定の間隔で間引くので、fps はプロジェクトのフレームレートを割り切れる値に限る。
    """
    if not 0 < seconds <= MAX_SECONDS:
        raise ValueError(f"長さは 0 秒より長く {MAX_SECONDS} 秒以下にしてください: {seconds}")
    if fps <= 0:
        raise ValueError(f"fps は正の値にしてください: {fps}")
    step = project_fps / fps
    if step.denominator != 1:
        raise ValueError(
            f"fps {fps} はプロジェクトのフレームレート {project_fps} を割り切れません。"
            "フレームの間隔が不揃いになるため、割り切れる値を指定してください"
        )
    count = max(1, round(seconds * fps))
    return [start + index * step.numerator for index in range(count)]


def fit_to_square(image: Image.Image, size: int, background: Color | None = None) -> Image.Image:
    """縦横比を保って size×size に収め、中央に置く。余白は background（None なら透明）。"""
    canvas = Image.new("RGBA", (size, size), _rgba(background))
    resized = shrink(image, size)
    canvas.alpha_composite(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
    return canvas


def shrink(image: Image.Image, max_size: int) -> Image.Image:
    """縦横比を保って、長い辺が max_size 以下になるよう縮小する（拡大はしない）。

    大きめに描画してから縮小すると、細い線もきれいに残る。
    Pillow は RGBA を縮小するとき、透明な画素の色が混ざらないよう乗算済みアルファで計算する。
    """
    image = image.convert("RGBA")
    scale = min(1.0, max_size / max(image.size))
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    if size == image.size:
        return image
    return image.resize(size, Image.Resampling.LANCZOS)


def save_animation(
    images: Sequence[Image.Image],
    path: Path,
    durations_ms: Sequence[int],
    *,
    quality: int = 80,
) -> Path:
    """images をアニメーション WebP / GIF として保存する。形式は path の拡張子で決める。

    GIF は透明を「透明か不透明か」の 2 段階でしか表せず、半透明の部分は不透明になる。
    GIF を使うときは、背景色を塗ってから渡すのがよい。
    """
    image_format = _format_of(path)
    if not images:
        raise ValueError("画像がありません")
    if len(durations_ms) != len(images):
        raise ValueError(f"画像 {len(images)} 枚に対して、表示時間が {len(durations_ms)} 個あります")
    path.parent.mkdir(parents=True, exist_ok=True)
    options: dict[str, object] = {
        "save_all": True,
        "append_images": list(images[1:]),
        "duration": list(durations_ms),
        "loop": 0,
    }
    if image_format == "WEBP":
        options["quality"] = quality
    else:
        # 前のフレームを消してから次を描く。消さないと透明な部分に前のフレームが残る。
        options["disposal"] = 2
    images[0].save(path, image_format, **options)
    return path


def make_thumbnail(
    environment: Environment,
    project: Project | Path,
    output_path: Path,
    *,
    seconds: float = DEFAULT_SECONDS,
    fps: int = DEFAULT_FPS,
    start: int = 0,
    size: int = THUMBNAIL_SIZE,
    background: Color | None = None,
    quality: int = 80,
    work_dir: Path | None = None,
    timeout: float | None = None,
) -> Path:
    """project を AviUtl2 で描画し、size×size の動くサムネイルを output_path に作る。

    project は Project か、AviUtl2 で保存した .aup2 のパス。
    形式は output_path の拡張子（.webp / .gif）で決める。
    environment は create_environment で作った検証用の環境。
    描画したフレームとプロジェクトは work_dir（既定は環境の隣の thumbnail フォルダ）に残る。
    """
    _format_of(output_path)
    work_dir = (work_dir or environment.root.parent / "thumbnail").resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(project, Project):
        project_path = work_dir / "project.aup2"
        project.write(project_path)
        project_fps = Fraction(project.rate, project.scale)
    else:
        project_path = project
        project_fps = read_frame_rate(project)

    frames = thumbnail_frames(project_fps, seconds, fps, start)
    if timeout is None:
        timeout = _TIMEOUT_BASE_SECONDS + _TIMEOUT_PER_FRAME_SECONDS * len(frames)
    result = render(environment, project_path, frames, work_dir, timeout)

    images = [fit_to_square(result.images[frame], size, background) for frame in frames]
    duration_ms = round(1000 / fps)
    save_animation(images, output_path, [duration_ms] * len(images), quality=quality)

    file_size = output_path.stat().st_size
    if file_size > WARNING_BYTES:
        warnings.warn(
            f"サムネイルが {file_size / 1024 / 1024:.1f}MB あります"
            f"（目安 {WARNING_BYTES // 1024 // 1024}MB）。"
            "fps・長さ・quality を下げると小さくなります",
            ThumbnailSizeWarning,
            stacklevel=2,
        )
    return output_path


def read_frame_rate(project_path: Path) -> Fraction:
    """.aup2 の最初のシーンから、フレームレート（video.rate / video.scale）を読む。"""
    text = project_path.read_text(encoding="utf-8-sig")
    rate = re.search(r"^video\.rate=(\d+)\s*$", text, re.MULTILINE)
    scale = re.search(r"^video\.scale=(\d+)\s*$", text, re.MULTILINE)
    if rate is None or scale is None:
        raise ValueError(
            f"プロジェクトからフレームレート（video.rate / video.scale）を読めません: {project_path}"
        )
    return Fraction(int(rate.group(1)), int(scale.group(1)))


def parse_color(text: str) -> Color:
    """ "#000000" や "white" などの色の指定を読む。"""
    return ImageColor.getrgb(text)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aviutl2-pyrrhulina-thumbnail",
        description="AviUtl2 で描画した結果から、AviUtl2 Catalog 用の動くサムネイルを作る",
    )
    parser.add_argument("project", type=Path, help="AviUtl2 で保存したプロジェクト（.aup2）")
    parser.add_argument("output", type=Path, help="出力するファイル（.webp または .gif）")
    parser.add_argument(
        "--app",
        type=Path,
        default=Path(os.environ.get("AVIUTL2_APP", DEFAULT_APP_DIR)),
        help="複製元の AviUtl2 のフォルダ（既定: 環境変数 AVIUTL2_APP、無ければ %(default)s）",
    )
    parser.add_argument(
        "--script",
        action="append",
        default=[],
        metavar="フォルダ名=パス",
        help="Script フォルダの下に置くフォルダ名と、その中身にするフォルダ（複数指定できる）",
    )
    parser.add_argument("--seconds", type=float, default=DEFAULT_SECONDS, help="長さ（秒、既定 %(default)s）")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help="fps（既定 %(default)s）")
    parser.add_argument("--start", type=int, default=0, help="開始フレーム（既定 %(default)s）")
    parser.add_argument("--size", type=int, default=THUMBNAIL_SIZE, help="一辺の大きさ（既定 %(default)s）")
    parser.add_argument("--background", type=parse_color, help="背景色（例: #000000）。省略すると透明")
    parser.add_argument("--quality", type=int, default=80, help="WebP の画質 0〜100（既定 %(default)s）")
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path(".aviutl2-pyrrhulina"),
        help="検証用の環境と途中のファイルを置くフォルダ（既定 %(default)s）",
    )
    args = parser.parse_args(argv)

    scripts = {}
    for item in args.script:
        name, separator, folder = item.partition("=")
        if not separator or not name or not folder:
            parser.error(f"--script は「フォルダ名=パス」の形で指定してください: {item}")
        scripts[name] = Path(folder)

    if not (args.app / "aviutl2.exe").exists():
        parser.error(f"AviUtl2 が見つかりません: {args.app}")
    environment = create_environment(args.work_dir / "app", args.app, scripts)
    output_path = make_thumbnail(
        environment,
        args.project,
        args.output,
        seconds=args.seconds,
        fps=args.fps,
        start=args.start,
        size=args.size,
        background=args.background,
        quality=args.quality,
        work_dir=args.work_dir / "thumbnail",
    )
    print(f"サムネイルを作りました: {output_path}（{output_path.stat().st_size / 1024:.0f}KB）")
    return 0


def _format_of(path: Path) -> str:
    image_format = _FORMATS.get(path.suffix.lower())
    if image_format is None:
        raise ValueError(f"拡張子は .webp か .gif にしてください: {path}")
    return image_format


def _rgba(color: Color | None) -> tuple[int, int, int, int]:
    if color is None:
        return (0, 0, 0, 0)
    if len(color) == 3:
        return (*color, 255)
    return color


if __name__ == "__main__":
    raise SystemExit(main())
