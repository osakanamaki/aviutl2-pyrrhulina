"""pytest から AviUtl2 を使うための fixture。

利用側の conftest.py で `aviutl2_scripts` を上書きして、検証するスクリプトを指定する:

    @pytest.fixture(scope="session")
    def aviutl2_scripts():
        return {"my-script-dev": Path(__file__).parent.parent / "script"}
"""

import json
import os
import re
import shutil
from collections.abc import Generator, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image

from aviutl2_pyrrhulina.compare import ImageComparison, ImageMismatch, compare_images
from aviutl2_pyrrhulina.environment import DEFAULT_APP_DIR, Environment, create_environment
from aviutl2_pyrrhulina.evidence import EvidenceRecord, write_frames_animation, write_report
from aviutl2_pyrrhulina.package import InstalledFile, Package
from aviutl2_pyrrhulina.project import Project
from aviutl2_pyrrhulina.runner import RenderResult, render

_WORK_DIR_NAME = ".aviutl2-pyrrhulina"
_REPORT_NAME = "index.html"

# テストごとの証跡を、pytest のテスト項目に持たせておく。一覧を作るときに集める。
_RECORD_KEY = pytest.StashKey[EvidenceRecord]()
_REPORT_PATH_KEY = pytest.StashKey[Path]()
_INSTALLED_FILES_KEY = pytest.StashKey[tuple[InstalledFile, ...]]()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("aviutl2")
    group.addoption(
        "--aviutl2-app",
        default=os.environ.get("AVIUTL2_APP", DEFAULT_APP_DIR),
        help="複製元の AviUtl2 のフォルダ（既定: 環境変数 AVIUTL2_APP、無ければ %(default)s）",
    )
    group.addoption(
        "--aviutl2-update-baselines",
        action="store_true",
        help="比較せずに、今回の描画結果で基準画像を書き換える",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "aviutl2: AviUtl2 を起動するテスト（fixture の使用で自動的に付く）")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "aviutl2" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.aviutl2)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, object, object]:
    report = yield
    record = item.stash.get(_RECORD_KEY, None)
    if record is not None and isinstance(report, pytest.TestReport):
        # 準備・本体・後片付けのどこかで失敗していれば、失敗として記録する。
        if report.failed:
            record.outcome = "failed"
            record.failure_text += report.longreprtext
        elif report.when == "call" or (report.when == "setup" and report.skipped):
            record.outcome = report.outcome
    return report


def pytest_sessionfinish(session: pytest.Session) -> None:
    records = [item.stash[_RECORD_KEY] for item in session.items if _RECORD_KEY in item.stash]
    if not records:
        return
    report_path = session.config.rootpath / _WORK_DIR_NAME / "evidence" / _REPORT_NAME
    write_report(report_path, records)
    session.config.stash[_REPORT_PATH_KEY] = report_path


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter, config: pytest.Config) -> None:
    report_path = config.stash.get(_REPORT_PATH_KEY, None)
    if report_path is not None:
        terminalreporter.write_line(f"AviUtl2 の描画結果の一覧: {report_path}")
    installed_files = config.stash.get(_INSTALLED_FILES_KEY, ())
    if installed_files:
        # カタログの登録フォームに書き写せるよう、カタログのデータと同じ形で出す。
        catalog_files = [installed_file.to_catalog() for installed_file in installed_files]
        terminalreporter.write_line("配布物から置いたファイル（カタログの version.file と同じ形）:")
        terminalreporter.write_line(json.dumps(catalog_files, ensure_ascii=False, indent=2))


@dataclass(frozen=True)
class AviUtl2:
    environment: Environment
    evidence_dir: Path
    update_baselines: bool
    record: EvidenceRecord
    # assert_snapshot の基準画像を置くフォルダ（このテスト専用）。
    snapshot_dir: Path
    # このテストで assert_snapshot に使った name。同じ基準画像を取り違えないようにするため。
    _snapshot_names: set[str] = field(default_factory=set)

    def render(
        self,
        project: Project,
        frames: Sequence[int],
        *,
        timeout: float = 60,
        allow_log_errors: bool = False,
        ignore_log_errors: Sequence[str] = (),
    ) -> RenderResult:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        project_path = self.evidence_dir / "project.aup2"
        project.write(project_path)
        # 1 つのテストで複数回描画したときは、最後の描画結果だけを一覧に載せる。
        self.record.frames = {}
        self.record.animation_path = None
        result = render(
            self.environment,
            project_path,
            frames,
            self.evidence_dir,
            timeout,
            allow_log_errors,
            ignore_log_errors,
        )
        self.record.frames = dict(result.image_paths)
        if len(result.images) >= 2:
            # 動きのある絵柄は、静止画を並べるより動かしたほうが確かめやすい。
            self.record.animation_path = write_frames_animation(
                result.images, Fraction(project.rate, project.scale), self.evidence_dir / "frames.webp"
            )
        return result

    def assert_matches(
        self, actual: Image.Image, baseline_path: Path, *, tolerance: int = 0
    ) -> ImageComparison:
        comparison = compare_images(
            actual, baseline_path, self.evidence_dir, tolerance=tolerance, update=self.update_baselines
        )
        # 一致しなくても一覧に載せられるよう、例外にする前に記録する。
        self.record.comparisons.append(comparison)
        if not comparison.passed:
            raise ImageMismatch(comparison.describe(), [comparison])
        return comparison

    def assert_snapshot(
        self, result: RenderResult, *, name: str = "", tolerance: int = 0
    ) -> list[ImageComparison]:
        """描画した全フレームを、テスト名から決まる基準画像と比べる。

        基準画像は <snapshot_dir>/frame_00005.png（name を付けたときは <snapshot_dir>/<name>/ の下）。
        1 つのテストで複数回描画したときは、name を付けて区別する。
        一致しないフレームがあっても途中で止めず、全フレームを比べてからまとめて報告する。
        """
        if name != _safe_name(name):
            raise ValueError(f"name にファイル名に使えない文字が含まれています: {name!r}")
        if name in self._snapshot_names:
            label = f"name={name!r} の" if name else "name を付けない"
            raise ValueError(
                f"このテストで {label} assert_snapshot が 2 回呼ばれました。name で区別してください"
            )
        self._snapshot_names.add(name)

        baseline_dir = self.snapshot_dir / name if name else self.snapshot_dir
        evidence_dir = self.evidence_dir / "snapshot" / name if name else self.evidence_dir / "snapshot"
        comparisons = []
        for frame, image in sorted(result.images.items()):
            comparison = compare_images(
                image,
                baseline_dir / f"frame_{frame:05d}.png",
                evidence_dir,
                tolerance=tolerance,
                update=self.update_baselines,
            )
            # 一致しなくても一覧に載せられるよう、例外にする前に記録する。
            self.record.comparisons.append(comparison)
            comparisons.append(comparison)

        failures = [comparison for comparison in comparisons if not comparison.passed]
        if failures:
            summary = f"{len(comparisons)} フレーム中 {len(failures)} フレームが基準画像と一致しません"
            raise ImageMismatch("\n".join([summary, *(failure.describe() for failure in failures)]), failures)
        return comparisons


@pytest.fixture(scope="session")
def aviutl2_scripts() -> Mapping[str, Path]:
    """Script フォルダの下に置くフォルダ名と、その中身にするフォルダ。"""
    return {}


@pytest.fixture(scope="session")
def aviutl2_plugins() -> Sequence[Path]:
    """Plugin フォルダに置くファイルかフォルダ（.auf2 など）。"""
    return ()


@pytest.fixture(scope="session")
def aviutl2_package() -> Package | None:
    """配布物とインストール手順。指定すると、手順どおりに置いてから検査する。"""
    return None


@pytest.fixture(scope="session")
def aviutl2_environment(
    pytestconfig: pytest.Config,
    aviutl2_scripts: Mapping[str, Path],
    aviutl2_plugins: Sequence[Path],
    aviutl2_package: Package | None,
) -> Environment:
    app_dir = Path(pytestconfig.getoption("--aviutl2-app"))
    if not (app_dir / "aviutl2.exe").exists():
        pytest.skip(f"AviUtl2 が見つかりません: {app_dir}")
    environment = create_environment(
        pytestconfig.rootpath / _WORK_DIR_NAME / "app",
        app_dir,
        aviutl2_scripts,
        plugins=aviutl2_plugins,
        package=aviutl2_package,
    )
    pytestconfig.stash[_INSTALLED_FILES_KEY] = environment.installed_files
    return environment


def _safe_name(text: str) -> str:
    """ファイル名に使えない文字を _ に置き換える。"""
    return re.sub(r'[<>:"/\\|?*\[\]]+', "_", text)


@pytest.fixture
def aviutl2_baselines(request: pytest.FixtureRequest) -> Path:
    """assert_snapshot の基準画像を置くフォルダ。既定はテストファイルと同じ場所の baselines。

    この下に <テストファイル名>/<テスト名>/ を作って基準画像を置く。
    """
    return request.path.parent / "baselines"


@pytest.fixture
def aviutl2(
    request: pytest.FixtureRequest, aviutl2_environment: Environment, aviutl2_baselines: Path
) -> AviUtl2:
    test_name = _safe_name(request.node.nodeid)
    evidence_dir = request.config.rootpath / _WORK_DIR_NAME / "evidence" / test_name
    # 前回の失敗で残った画像を、今回の結果と取り違えないようにする。
    shutil.rmtree(evidence_dir, ignore_errors=True)
    record = EvidenceRecord(request.node.nodeid, evidence_dir)
    request.node.stash[_RECORD_KEY] = record
    # テスト名にはパラメータ化の [...] も含める。
    snapshot_dir = aviutl2_baselines / request.path.stem / _safe_name(request.node.name)
    return AviUtl2(
        aviutl2_environment,
        evidence_dir,
        request.config.getoption("--aviutl2-update-baselines"),
        record,
        snapshot_dir,
    )
