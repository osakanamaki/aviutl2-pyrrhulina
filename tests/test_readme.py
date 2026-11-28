"""README の構成図（docs/images/overview-*.svg）の食い違いを見つけるテスト。"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
IMAGES = ROOT / "docs" / "images"
REPOSITORY_RAW_URL = "https://raw.githubusercontent.com/osakanamaki/aviutl2-pyrrhulina"


def _project_version() -> str:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["project"]["version"]


def _without_colors(svg: str) -> str:
    """ライト用とダーク用で異なってよい部分（冒頭のコメントと <style>）を取り除く。"""
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.DOTALL)
    return re.sub(r"<style>.*?</style>", "", svg, flags=re.DOTALL)


def test_light_and_dark_diagrams_differ_only_in_colors() -> None:
    light = (IMAGES / "overview-light.svg").read_text(encoding="utf-8")
    dark = (IMAGES / "overview-dark.svg").read_text(encoding="utf-8")

    assert _without_colors(light) == _without_colors(dark)


def test_readme_diagrams_point_to_this_version_tag() -> None:
    # PyPI では相対パスが解決されないため、README の図はタグ付きの絶対 URL で参照する。
    # main を指すとリリース版と図の内容がずれるので、pyproject.toml の version と同じタグを指す。
    readme = README.read_text(encoding="utf-8")
    urls = re.findall(r'(?:src|srcset)="([^"]+\.svg)"', readme)
    expected_prefix = f"{REPOSITORY_RAW_URL}/v{_project_version()}/"

    assert urls, "README に構成図の SVG が見つかりません"
    for url in urls:
        assert url.startswith(expected_prefix), url
        assert (ROOT / url.removeprefix(expected_prefix)).is_file(), url
