"""AviUtl2 を起動し、検証用プラグインにフレームを描画させて結果を受け取る。"""

import os
import struct
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from aviutl2_pyrrhulina.environment import Environment
from aviutl2_pyrrhulina.project import PreviewTarget

JOB_ENV_VAR = "AVIUTL2_PYRRHULINA_JOB"

# プラグインには、こちらの制限時間よりこれだけ早く諦めさせる。
# こちらが先に AviUtl2 を止めると、どの手順で止まったかが分からなくなるため。
_PLUGIN_MARGIN_SECONDS = 5

# 検証用プラグインが求める一番古い本体（plugin/agent.cpp の kRequiredVersion と合わせる）。
MINIMUM_AVIUTL2_VERSION = "2.1.17"
# 本体が RequiredVersion を満たさないとき、AviUtl2 がログに出す文言。
_VERSION_NOT_SUPPORTED = "version not supported"


class AviUtl2Error(Exception):
    pass


@dataclass(frozen=True)
class RenderResult:
    images: dict[int, Image.Image]
    log: str
    # 証跡として保存した各フレームの PNG。
    image_paths: dict[int, Path] = field(default_factory=dict)

    def log_lines(self, containing: str) -> list[str]:
        """スクリプトの print は「[SCRIPT] [スクリプト名] 本文」の形で出る。

        プレビュー表示のためにも描画が走るので、同じ行が複数回出る。回数は当てにできない。
        """
        return [line for line in self.log.splitlines() if containing in line]

    @property
    def log_errors(self) -> list[str]:
        """エラーを示すログ行。Lua の実行時エラーは [WARN] の "script exception" として出る。"""
        return [line for line in self.log.splitlines() if "[ERROR]" in line or "script exception" in line]


def render(
    environment: Environment,
    project_path: Path,
    frames: Sequence[int],
    work_dir: Path,
    timeout: float = 60,
    allow_log_errors: bool = False,
    ignore_log_errors: Sequence[str] = (),
    preview: PreviewTarget | None = None,
) -> RenderResult:
    """project_path を開いて frames を描画する。画像とログは work_dir にも残す。

    スクリプトがエラーになっても AviUtl2 は止まらず、何も描画されないだけになる。
    見落とさないよう、ログにエラーがあれば例外にする。
    起きると分かっているエラーは、その行に含まれる文字列を ignore_log_errors に渡して除外する。
    allow_log_errors=True なら、どのエラーでも例外にしない。

    preview を渡すと、出力ではなくプレビューとして描画する。そのとき選択したオブジェクトでは
    obj.getoption("gui") が true になる。project_path のプロジェクトは、
    add_preview_capture で受け取り用のオブジェクトを足したものにしておく。
    """
    # AviUtl2 側は作業フォルダが違うので、渡すパスはすべて絶対パスにする。
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    project_path = project_path.resolve()
    raw_paths = {frame: work_dir / f"frame_{frame:05d}.rgba" for frame in frames}
    job_path = work_dir / "job.txt"
    result_path = Path(f"{job_path}.result")
    result_path.unlink(missing_ok=True)
    plugin_timeout = max(timeout - _PLUGIN_MARGIN_SECONDS, timeout / 2)
    job_lines = [
        f"timeout\t{round(plugin_timeout * 1000)}",
        f"project\t{project_path}",
    ]
    if preview is None:
        job_lines += [f"render\t{frame}\t{path}" for frame, path in raw_paths.items()]
    else:
        job_lines.append(f"select\t{preview.selected_layer}\t{preview.selected_frame}")
        job_lines += [
            f"preview\t{frame}\t{preview.marker_layer}\t{path}" for frame, path in raw_paths.items()
        ]
    job_path.write_text("\n".join(job_lines) + "\n", encoding="utf-8")

    logs_before = set(environment.log_dir.glob("*.log"))
    process = subprocess.Popen(
        [str(environment.exe), str(project_path)],
        cwd=environment.root,
        env={**os.environ, JOB_ENV_VAR: str(job_path)},
    )
    try:
        process.wait(timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        timed_out = True

    # AviUtl2 のログは Shift_JIS で書かれる。
    new_logs = sorted(set(environment.log_dir.glob("*.log")) - logs_before)
    log = "".join(path.read_text(encoding="cp932", errors="replace") for path in new_logs)
    log_path = work_dir / "aviutl2.log"
    log_path.write_text(log, encoding="utf-8")

    # 描画が終わらないときは、プラグインが結果を書いた後も AviUtl2 が閉じない。
    # その場合も、どの手順で止まったかを伝えられるよう、結果を先に読む。
    errors = []
    if result_path.exists():
        errors = _result_errors(job_lines, result_path.read_text(encoding="utf-8"))
    elif not timed_out:
        errors = ["AviUtl2 が結果を書かずに終了しました（異常終了の可能性）"]
    if timed_out:
        errors.append(f"AviUtl2 が {timeout} 秒以内に終了しなかったので、強制終了しました")
    if _VERSION_NOT_SUPPORTED in log:
        # 本体が古いと、AviUtl2 はダイアログを出して止まり、時間切れになる。原因が分かるよう先頭に出す。
        errors.insert(
            0,
            "AviUtl2 本体が古いため、検証用プラグインが読み込まれませんでした。"
            f"AviUtl2 を {MINIMUM_AVIUTL2_VERSION} 以上に更新してください",
        )
    if not new_logs:
        # ログが無いと、ログのエラー検出が何も見つけられずに素通りしてしまう。
        errors.append(f"AviUtl2 のログファイルが新しく作られませんでした: {environment.log_dir}")
    if errors:
        raise AviUtl2Error("\n".join([*errors, f"ログ: {log_path}"]))

    images = {}
    image_paths = {}
    for frame, raw_path in raw_paths.items():
        images[frame] = _read_raw_image(raw_path)
        image_paths[frame] = raw_path.with_suffix(".png")
        images[frame].save(image_paths[frame])
        raw_path.unlink()
    result = RenderResult(images, log, image_paths)
    unexpected = [
        line for line in result.log_errors if not any(ignored in line for ignored in ignore_log_errors)
    ]
    if unexpected and not allow_log_errors:
        raise AviUtl2Error("\n".join(["ログにエラーがあります:", *unexpected, f"ログ: {log_path}"]))
    return result


def _result_errors(job_lines: Sequence[str], result_text: str) -> list[str]:
    """プラグインの結果ファイル（命令と同じ順に 1 行ずつ）から、失敗した命令を取り出す。"""
    results = [line.split("\t") for line in result_text.splitlines()]
    errors = [
        f"{command}: {' '.join(result[1:])}"
        for command, result in zip(job_lines, results, strict=False)
        if result[0] != "ok"
    ]
    if len(results) != len(job_lines):
        # プラグインがジョブファイルを読めなかったときなど。
        errors.append(f"プラグインの結果が {len(results)} 行で、命令の {len(job_lines)} 行と合いません")
    return errors


def _read_raw_image(path: Path) -> Image.Image:
    data = path.read_bytes()
    width, height, pitch = struct.unpack_from("<3i", data)
    return Image.frombuffer("RGBA", (width, height), data[12:], "raw", "RGBA", pitch, 1).copy()
