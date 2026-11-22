import json
import zipfile
from pathlib import Path

import pytest
import xxhash

from aviutl2_pyrrhulina import InstallStep, Package, PackageError, install_package, load_install_steps
from aviutl2_pyrrhulina.environment import AGENT_PLUGIN, create_environment
from aviutl2_pyrrhulina.package import main


def _archive(tmp_path: Path, files: dict[str, bytes]) -> Path:
    path = tmp_path / "dist" / "my-package.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def _steps(*steps: dict[str, str]) -> list[InstallStep]:
    return [InstallStep.from_dict(step) for step in steps]


def _install(tmp_path: Path, archive: Path, steps: list[InstallStep]):  # noqa: ANN202
    app_dir = tmp_path / "app"
    return install_package(Package(archive, steps), app_dir, app_dir / "data", tmp_path / "tmp")


_DOWNLOAD_AND_EXTRACT = ({"action": "download"}, {"action": "extract"})


def test_files_are_placed_as_install_steps_say(tmp_path: Path) -> None:
    archive = _archive(tmp_path, {"MyPlugin/my.auf2": b"plugin", "MyPlugin/readme.txt": b"readme"})

    installed = _install(
        tmp_path,
        archive,
        _steps(
            *_DOWNLOAD_AND_EXTRACT, {"action": "copy", "from": "{tmp}/MyPlugin/my.auf2", "to": "{pluginsDir}"}
        ),
    )

    assert (tmp_path / "app" / "data" / "Plugin" / "my.auf2").read_bytes() == b"plugin"
    assert [file.to_catalog() for file in installed] == [
        {"path": "{pluginsDir}/my.auf2", "XXH3_128": xxhash.xxh3_128_hexdigest(b"plugin")}
    ]


def test_folder_is_copied_with_its_contents(tmp_path: Path) -> None:
    archive = _archive(tmp_path, {"Script/a.anm2": b"a", "Script/sub/b.obj2": b"b"})

    installed = _install(
        tmp_path,
        archive,
        _steps(
            *_DOWNLOAD_AND_EXTRACT, {"action": "copy", "from": "{tmp}/Script", "to": "{scriptsDir}/my-script"}
        ),
    )

    assert sorted(file.catalog_path for file in installed) == [
        "{scriptsDir}/my-script/a.anm2",
        "{scriptsDir}/my-script/sub/b.obj2",
    ]


def test_delete_removes_placed_file(tmp_path: Path) -> None:
    archive = _archive(tmp_path, {"a.auf2": b"a", "b.auf2": b"b"})

    installed = _install(
        tmp_path,
        archive,
        _steps(
            *_DOWNLOAD_AND_EXTRACT,
            {"action": "copy", "from": "{tmp}/a.auf2", "to": "{pluginsDir}"},
            {"action": "copy", "from": "{tmp}/b.auf2", "to": "{pluginsDir}"},
            {"action": "delete", "path": "{pluginsDir}/b.auf2"},
        ),
    )

    assert [file.catalog_path for file in installed] == ["{pluginsDir}/a.auf2"]
    assert not (tmp_path / "app" / "data" / "Plugin" / "b.auf2").exists()


def test_copy_of_missing_file_is_an_error(tmp_path: Path) -> None:
    archive = _archive(tmp_path, {"a.auf2": b"a"})

    with pytest.raises(PackageError, match="手順 3.*コピーするファイルがありません"):
        _install(
            tmp_path,
            archive,
            _steps(
                *_DOWNLOAD_AND_EXTRACT, {"action": "copy", "from": "{tmp}/none.auf2", "to": "{pluginsDir}"}
            ),
        )


def test_outside_of_environment_is_an_error(tmp_path: Path) -> None:
    archive = _archive(tmp_path, {"a.auf2": b"a"})

    with pytest.raises(PackageError, match="検証用の環境の外"):
        _install(
            tmp_path,
            archive,
            _steps(
                *_DOWNLOAD_AND_EXTRACT, {"action": "copy", "from": "{tmp}/a.auf2", "to": "{appDir}/../.."}
            ),
        )


def test_download_must_come_before_extract(tmp_path: Path) -> None:
    archive = _archive(tmp_path, {"a.auf2": b"a"})

    with pytest.raises(PackageError, match="download より前"):
        _install(tmp_path, archive, _steps({"action": "extract"}))


@pytest.mark.parametrize("action", ["run", "extract_sfx", "run_auo_setup"])
def test_actions_running_programs_are_not_supported(tmp_path: Path, action: str) -> None:
    archive = _archive(tmp_path, {"a.auf2": b"a"})

    with pytest.raises(PackageError, match="対応していません"):
        _install(tmp_path, archive, _steps({"action": "download"}, {"action": action, "path": "{download}"}))


@pytest.mark.parametrize(
    "data",
    [
        [{"action": "download"}],
        {"install": [{"action": "download"}]},
        {"installer": {"install": [{"action": "download"}], "uninstall": []}},
    ],
)
def test_install_steps_are_read_in_catalog_forms(tmp_path: Path, data: object) -> None:
    path = tmp_path / "install.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    assert load_install_steps(path) == [InstallStep("download")]


def test_command_prints_hashes_in_catalog_form(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    archive = _archive(tmp_path, {"my.auf2": b"plugin"})
    install_json = tmp_path / "install.json"
    steps = [*_DOWNLOAD_AND_EXTRACT, {"action": "copy", "from": "{tmp}/my.auf2", "to": "{pluginsDir}"}]
    install_json.write_text(json.dumps(steps), encoding="utf-8")

    assert main([str(archive), str(install_json)]) == 0

    assert json.loads(capsys.readouterr().out) == [
        {"path": "{pluginsDir}/my.auf2", "XXH3_128": xxhash.xxh3_128_hexdigest(b"plugin")}
    ]


@pytest.mark.skipif(not AGENT_PLUGIN.exists(), reason="検証用プラグインがビルドされていません")
def test_placed_plugins_and_package_files_are_trusted(tmp_path: Path) -> None:
    app_dir = tmp_path / "AviUtl2"
    app_dir.mkdir()
    (app_dir / "aviutl2.exe").write_bytes(b"")
    plugin = tmp_path / "dev" / "my.auf2"
    plugin.parent.mkdir()
    plugin.write_bytes(b"")
    archive = _archive(tmp_path, {"Pkg/x.aux2": b"", "Pkg/y.anm2": b""})
    package = Package(
        archive,
        _steps(
            *_DOWNLOAD_AND_EXTRACT,
            {"action": "copy", "from": "{tmp}/Pkg/x.aux2", "to": "{pluginsDir}/Pkg"},
            {"action": "copy", "from": "{tmp}/Pkg/y.anm2", "to": "{scriptsDir}/Pkg"},
        ),
    )

    environment = create_environment(tmp_path / "env" / "app", app_dir, {}, plugins=[plugin], package=package)

    module_ini = (environment.data_dir / "module.ini").read_text(encoding="utf-8")
    for name in ["aviutl2_pyrrhulina.aux2", "my.auf2", "Pkg\\x.aux2", "Pkg\\y.anm2"]:
        assert f"[{name}]" in module_ini
    assert [file.catalog_path for file in environment.installed_files] == [
        "{pluginsDir}/Pkg/x.aux2",
        "{scriptsDir}/Pkg/y.anm2",
    ]


def test_fixture_places_package_and_prints_hashes(pytester: pytest.Pytester, tmp_path: Path) -> None:
    if not AGENT_PLUGIN.exists():
        pytest.skip("検証用プラグインがビルドされていません")
    # aviutl2.exe は起動しないので、空のファイルで足りる。
    app_dir = tmp_path / "AviUtl2"
    app_dir.mkdir()
    (app_dir / "aviutl2.exe").write_bytes(b"")
    archive = _archive(tmp_path, {"my.auf2": b"plugin"})
    pytester.makeconftest(
        "import pytest\n"
        "from pathlib import Path\n"
        "from aviutl2_pyrrhulina import InstallStep, Package\n"
        "@pytest.fixture(scope='session')\n"
        "def aviutl2_package():\n"
        "    steps = [{'action': 'download'}, {'action': 'extract'},\n"
        "             {'action': 'copy', 'from': '{tmp}/my.auf2', 'to': '{pluginsDir}'}]\n"
        f"    return Package(Path(r'{archive}'), [InstallStep.from_dict(step) for step in steps])\n"
    )
    pytester.makepyfile(
        "def test_environment(aviutl2_environment):\n"
        "    assert (aviutl2_environment.plugin_dir / 'my.auf2').exists()\n"
    )

    result = pytester.runpytest("--aviutl2-app", str(app_dir))

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(
        ['*"path": "{pluginsDir}/my.auf2"*', f'*"XXH3_128": "{xxhash.xxh3_128_hexdigest(b"plugin")}"*']
    )
