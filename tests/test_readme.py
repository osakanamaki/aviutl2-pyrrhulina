"""README の構成図（docs/images/overview-*.svg）の食い違いを見つけるテスト。"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
IMAGES = ROOT / "docs" / "images"
MAIN_RAW_URL = "https://raw.githubusercontent.com/osakanamaki/aviutl2-pyrrhulina/main/"


def _without_colors(svg: str) -> str:
    """ライト用とダーク用で異なってよい部分（冒頭のコメントと <style>）を取り除く。"""
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.DOTALL)
    return re.sub(r"<style>.*?</style>", "", svg, flags=re.DOTALL)


def test_light_and_dark_diagrams_differ_only_in_colors() -> None:
    light = (IMAGES / "overview-light.svg").read_text(encoding="utf-8")
    dark = (IMAGES / "overview-dark.svg").read_text(encoding="utf-8")

    assert _without_colors(light) == _without_colors(dark)


def test_readme_diagrams_point_to_existing_files_on_main() -> None:
    # PyPI では相対パスが解決されないため、README の図は main を指す絶対 URL で参照する。
    # 過去のバージョンの PyPI ページも同じ URL を読み込むので、参照先のファイルは消さない。
    readme = README.read_text(encoding="utf-8")
    urls = re.findall(r'(?:src|srcset)="([^"]+\.svg)"', readme)

    assert urls, "README に構成図の SVG が見つかりません"
    for url in urls:
        assert url.startswith(MAIN_RAW_URL), url
        assert (ROOT / url.removeprefix(MAIN_RAW_URL)).is_file(), url
