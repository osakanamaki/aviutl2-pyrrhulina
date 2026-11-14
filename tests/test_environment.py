import time
from pathlib import Path

import pytest

from aviutl2_pyrrhulina import create_environment, environment


@pytest.fixture(autouse=True)
def fake_agent_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """プラグインをビルドしていなくても、このファイルのテストは動くようにする。"""
    plugin = tmp_path / "agent.aux2"
    plugin.write_bytes(b"")
    monkeypatch.setattr(environment, "AGENT_PLUGIN", plugin)


def _fake_app(tmp_path: Path) -> Path:
    app_dir = tmp_path / "installed"
    app_dir.mkdir()
    (app_dir / "aviutl2.exe").write_bytes(b"")
    return app_dir


def test_environment_is_rebuilt_from_scratch(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "a.obj2").write_text("")
    root = tmp_path / "app"
    created = create_environment(root, _fake_app(tmp_path), {"mine": scripts})
    (created.data_dir / "leftover.ini").write_text("")

    created = create_environment(root, tmp_path / "installed", {"mine": scripts})

    assert not (created.data_dir / "leftover.ini").exists()
    assert (created.data_dir / "Script" / "mine" / "a.obj2").exists()
    assert r"[mine\a.obj2]" in (created.data_dir / "module.ini").read_text(encoding="utf-8")


def test_undeletable_environment_is_reported_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    root = tmp_path / "app"
    created = create_environment(root, _fake_app(tmp_path), {})

    # Windows では、開いているファイルは消せない（AviUtl2 が起動したままの状態に相当）。
    with (created.data_dir / "module.ini").open(), pytest.raises(RuntimeError, match="消せませんでした"):
        create_environment(root, tmp_path / "installed", {})
