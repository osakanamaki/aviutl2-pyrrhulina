"""普段の AviUtl2 から切り離した、検証専用の実行環境を作る。"""

import shutil
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from aviutl2_pyrrhulina.package import InstalledFile, Package, install_package

AGENT_PLUGIN = Path(__file__).parent / "_bin" / "aviutl2_pyrrhulina.aux2"

# 複製元の AviUtl2 の既定のフォルダ（インストーラーの既定のインストール先）。
DEFAULT_APP_DIR = r"C:\Program Files\AviUtl2"

# 信頼済みとして登録する（しないと初回起動時に確認ダイアログが出て止まる）ファイルの拡張子。
_SCRIPT_SUFFIXES = {".anm2", ".obj2", ".cam2", ".scn2", ".tra2", ".mod2"}
_PLUGIN_SUFFIXES = {".aux2", ".auf2", ".aui2", ".auo2"}
_MODULE_SUFFIXES = _SCRIPT_SUFFIXES | _PLUGIN_SUFFIXES

# FileLogLevel を書かないと、ログがファイルに出ない。1 は最も詳しいレベル。
_AVIUTL2_INI = "[Logger]\nFileLogLevel=1\n"


@dataclass(frozen=True)
class Environment:
    root: Path
    # 配布物（package）をインストール手順どおりに置いたときの、置いたファイル。
    installed_files: tuple[InstalledFile, ...] = ()

    @property
    def exe(self) -> Path:
        return self.root / "aviutl2.exe"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "Log"

    @property
    def plugin_dir(self) -> Path:
        return self.data_dir / "Plugin"

    @property
    def script_dir(self) -> Path:
        return self.data_dir / "Script"


def create_environment(
    root: Path,
    app_dir: Path,
    scripts: Mapping[str, Path],
    plugins: Sequence[Path] = (),
    package: Package | None = None,
) -> Environment:
    """app_dir の AviUtl2 を root に複製し、検査するものを配置する。

    scripts は Script フォルダの下に置くフォルダ名と、その中身にするフォルダ。
    plugins は Plugin フォルダに置くファイルかフォルダ（フォルダはその名前のまま Plugin の下に置く）。
    package は配布物とインストール手順。手順どおりに置く。

    実行ファイルと同じ場所に data フォルダがあると、AviUtl2 は設定の保存先を
    ProgramData からそこへ切り替える。これで普段の環境に触れずに済む。
    """
    if not AGENT_PLUGIN.exists():
        raise FileNotFoundError(
            f"検証用プラグインがありません。`task build` を実行してください: {AGENT_PLUGIN}"
        )
    if not (app_dir / "aviutl2.exe").exists():
        raise FileNotFoundError(f"aviutl2.exe が見つかりません: {app_dir}")

    environment = Environment(root)
    # 前回の設定やスクリプトが結果に影響しないよう、毎回作り直す。
    _remove_tree(environment.data_dir)

    root.mkdir(parents=True, exist_ok=True)
    for source in app_dir.iterdir():
        if source.is_file() and source.name.lower() != "aviutl2_setup.exe":
            shutil.copy2(source, root / source.name)

    environment.plugin_dir.mkdir(parents=True)
    environment.script_dir.mkdir()
    shutil.copy2(AGENT_PLUGIN, environment.plugin_dir / AGENT_PLUGIN.name)
    for folder_name, source_dir in scripts.items():
        shutil.copytree(source_dir, environment.script_dir / folder_name)
    for source in plugins:
        if source.is_dir():
            shutil.copytree(source, environment.plugin_dir / source.name)
        elif source.is_file():
            shutil.copy2(source, environment.plugin_dir / source.name)
        else:
            raise FileNotFoundError(f"プラグインが見つかりません: {source}")

    installed: list[InstalledFile] = []
    if package is not None:
        tmp_dir = root.parent / "package-tmp"
        _remove_tree(tmp_dir)
        installed = install_package(package, root, environment.data_dir, tmp_dir)

    # 置いたものをすべて信頼済みとして登録する。
    # 名前は Plugin・Script フォルダからの相対パス（AviUtl2 が読むのは一つ下のフォルダまで）。
    trusted = _modules_in(environment.plugin_dir) + _modules_in(environment.script_dir)
    module_ini = "".join(f"[{name}]\ntrust=1\n" for name in trusted)
    (environment.data_dir / "module.ini").write_text(module_ini, encoding="utf-8", newline="\r\n")
    (environment.data_dir / "aviutl2.ini").write_text(_AVIUTL2_INI, encoding="utf-8", newline="\r\n")
    return Environment(root, tuple(installed))


def _modules_in(folder: Path) -> list[str]:
    """folder の直下と一つ下のフォルダにある、信頼済みとして登録するファイルの名前。"""
    candidates = [*folder.glob("*"), *folder.glob("*/*")]
    modules = [path for path in candidates if path.is_file() and path.suffix.lower() in _MODULE_SUFFIXES]
    return sorted(str(path.relative_to(folder)) for path in modules)


def _remove_tree(path: Path) -> None:
    # 直前に止めた AviUtl2 がファイルを掴んでいることがあるので、少し待って再試行する。
    for _ in range(10):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.3)
    raise RuntimeError(
        f"検証用の環境を消せませんでした: {path}\n"
        "この環境の AviUtl2 が起動したままになっていないか確認してください。"
    )
