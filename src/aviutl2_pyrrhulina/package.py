"""配布物（zip）を、AviUtl2 Catalog のインストール手順どおりに検証用の環境へ置く。

インストール手順は、カタログのデータ（index.json の installer.install）と同じ形の JSON で書く:

    [
      {"action": "download"},
      {"action": "extract"},
      {"action": "copy", "from": "{tmp}/my-plugin.auf2", "to": "{pluginsDir}"}
    ]

download はネットワークから取得する代わりに、手元の配布物（archive）を使う。
置いたファイルの XXH3_128 は、カタログに登録する値（version.file）と同じ形で出力できる。
"""

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import xxhash

# 対応していない手順。どれも外部のプログラムを実行するので、検証用の環境では再現しない。
_UNSUPPORTED_ACTIONS = {"run", "extractSfx", "extract_sfx", "runAuoSetup", "run_auo_setup"}


class PackageError(Exception):
    pass


@dataclass(frozen=True)
class InstallStep:
    """インストール手順の 1 つ。項目はカタログのデータと同じ。"""

    action: str
    from_: str = ""
    to: str = ""
    path: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "InstallStep":
        return cls(
            action=str(data.get("action", "")),
            from_=str(data.get("from", "")),
            to=str(data.get("to", "")),
            path=str(data.get("path", "")),
        )


@dataclass(frozen=True)
class Package:
    """配布物と、そのインストール手順。"""

    archive: Path
    install: Sequence[InstallStep]

    @classmethod
    def from_json(cls, archive: Path, install_json: Path) -> "Package":
        return cls(archive, load_install_steps(install_json))


@dataclass(frozen=True)
class InstalledFile:
    """インストール手順で置いたファイル。"""

    path: Path
    # カタログに書くパス（例: "{pluginsDir}/my-plugin.auf2"）。
    catalog_path: str
    xxh3_128: str

    def to_catalog(self) -> dict[str, str]:
        """カタログのデータ（version.file の要素）と同じ形。"""
        return {"path": self.catalog_path, "XXH3_128": self.xxh3_128}


def load_install_steps(install_json: Path) -> list[InstallStep]:
    """インストール手順の JSON を読む。

    手順の配列のほか、カタログのデータと同じ形の {"install": [...]} や
    {"installer": {"install": [...]}} も読める。
    """
    data = json.loads(install_json.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict) and "installer" in data:
        data = data["installer"]
    if isinstance(data, dict) and "install" in data:
        data = data["install"]
    if not isinstance(data, list) or not all(isinstance(step, dict) for step in data):
        raise PackageError(f"インストール手順の配列が見つかりません: {install_json}")
    return [InstallStep.from_dict(step) for step in data]


def file_hash(path: Path) -> str:
    """カタログと同じ XXH3_128（小文字 16 進数 32 桁）。"""
    digest = xxhash.xxh3_128()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_package(package: Package, app_dir: Path, data_dir: Path, tmp_dir: Path) -> list[InstalledFile]:
    """package をインストール手順どおりに置き、置いたファイルを返す。

    app_dir は AviUtl2 本体のフォルダ（{appDir}）、data_dir は設定やプラグインを置くフォルダ（{dataDir}）。
    tmp_dir は展開などに使う一時フォルダ（{tmp}）。
    手順で指定できる置き場所は、この 3 つのフォルダの中だけ（検証用の環境の外を書き換えないため）。
    """
    if not package.archive.is_file():
        raise PackageError(f"配布物がありません: {package.archive}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    # {download} は download の手順を実行してから使えるようになる。
    macros: dict[str, Path | None] = {
        "{download}": None,
        "{tmp}": tmp_dir.resolve(),
        "{appDir}": app_dir.resolve(),
        "{pluginsDir}": (data_dir / "Plugin").resolve(),
        "{scriptsDir}": (data_dir / "Script").resolve(),
        "{dataDir}": data_dir.resolve(),
    }
    allowed_roots = [tmp_dir.resolve(), app_dir.resolve(), data_dir.resolve()]
    copied: list[Path] = []

    for number, step in enumerate(package.install, start=1):
        label = f"手順 {number}（{step.action}）"
        if step.action == "download":
            # ネットワークから取得する代わりに、手元の配布物を一時フォルダに置く。
            download_path = tmp_dir.resolve() / package.archive.name
            shutil.copy2(package.archive, download_path)
            macros["{download}"] = download_path
        elif step.action == "extract":
            source = _expand(step.from_ or "{download}", macros, allowed_roots, label)
            destination = _expand(step.to or "{tmp}", macros, allowed_roots, label)
            try:
                with zipfile.ZipFile(source) as archive:
                    # 「..」や絶対パスの項目は、zipfile が展開先の中に収めてくれる。
                    archive.extractall(destination)
            except (OSError, zipfile.BadZipFile) as error:
                raise PackageError(f"{label}: zip を展開できません: {source}（{error}）") from error
        elif step.action == "copy":
            source = _expand(step.from_, macros, allowed_roots, label)
            destination = _expand(step.to, macros, allowed_roots, label)
            copied += _copy(source, destination, label)
        elif step.action == "delete":
            target = _expand(step.path, macros, allowed_roots, label)
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
            copied = [path for path in copied if not path.is_relative_to(target)]
        elif step.action in _UNSUPPORTED_ACTIONS:
            raise PackageError(f"{label}: この手順には対応していません（外部のプログラムを実行するため）")
        else:
            raise PackageError(f"{label}: 不明な手順です")

    catalog_roots = [
        ("{pluginsDir}", (data_dir / "Plugin").resolve()),
        ("{scriptsDir}", (data_dir / "Script").resolve()),
        ("{dataDir}", data_dir.resolve()),
        ("{appDir}", app_dir.resolve()),
    ]
    installed = []
    for path in dict.fromkeys(copied):  # 同じファイルに何度コピーしても 1 つにまとめる
        # 一時フォルダへのコピーは、インストールしたファイルではない。
        if path.is_relative_to(tmp_dir.resolve()):
            continue
        installed.append(InstalledFile(path, _catalog_path(path, catalog_roots), file_hash(path)))
    return installed


def _expand(text: str, macros: Mapping[str, Path | None], allowed_roots: Sequence[Path], label: str) -> Path:
    """{tmp} などのマクロを置き換えた絶対パス。検証用の環境の外を指すときは失敗する。"""
    if not text:
        raise PackageError(f"{label}: パスが指定されていません")
    value = text
    for macro, directory in macros.items():
        if macro not in value:
            continue
        if directory is None:
            raise PackageError(f"{label}: download より前に {macro} は使えません")
        value = value.replace(macro, str(directory))
    path = Path(value)
    if not path.is_absolute():
        raise PackageError(f"{label}: パスが絶対パスになりません: {text}")
    path = path.resolve()
    if not any(path.is_relative_to(root) for root in allowed_roots):
        raise PackageError(f"{label}: 検証用の環境の外は指定できません: {path}")
    return path


def _copy(source: Path, destination_dir: Path, label: str) -> list[Path]:
    """カタログと同じく、ファイルはフォルダの中へ、フォルダは中身をフォルダの中へコピーする。"""
    if source.is_file():
        destination_dir.mkdir(parents=True, exist_ok=True)
        return [Path(shutil.copy2(source, destination_dir / source.name))]
    if source.is_dir():
        copied = []
        for path in sorted(source.rglob("*")):
            if path.is_file():
                target = destination_dir / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                copied.append(Path(shutil.copy2(path, target)))
        if copied:
            return copied
    raise PackageError(f"{label}: コピーするファイルがありません: {source}")


def _catalog_path(path: Path, roots: Sequence[tuple[str, Path]]) -> str:
    for macro, root in roots:
        if path.is_relative_to(root):
            return f"{macro}/{path.relative_to(root).as_posix()}"
    raise ValueError(f"検証用の環境の外のファイルです: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aviutl2-pyrrhulina-package",
        description=(
            "配布物をインストール手順どおりに一時フォルダへ置き、置いたファイルの XXH3_128 を"
            "カタログのデータ（version.file）と同じ形の JSON で出力する（AviUtl2 は使わない）"
        ),
    )
    parser.add_argument("archive", type=Path, help="配布物（zip など）")
    parser.add_argument("install_json", type=Path, help="インストール手順の JSON")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="aviutl2-pyrrhulina-") as work:
        work_dir = Path(work)
        try:
            installed = install_package(
                Package.from_json(args.archive, args.install_json),
                work_dir / "app",
                work_dir / "app" / "data",
                work_dir / "tmp",
            )
        except PackageError as error:
            print(error, file=sys.stderr)
            return 1
    print(json.dumps([file.to_catalog() for file in installed], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
