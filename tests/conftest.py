from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def aviutl2_scripts() -> dict[str, Path]:
    return {"pyrrhulina-tests": Path(__file__).parent / "scripts"}
