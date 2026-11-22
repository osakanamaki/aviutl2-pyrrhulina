from pathlib import Path

import pytest

# プラグインの振る舞い（証跡の一覧など）を、別の pytest の実行で確かめるため。
pytest_plugins = ["pytester"]


@pytest.fixture(scope="session")
def aviutl2_scripts() -> dict[str, Path]:
    return {"pyrrhulina-tests": Path(__file__).parent / "scripts"}
