"""pytest-xdist で並列に実行したとき、AviUtl2 を起動するテストを止めることを確かめる。

xdist は依存に入れていないので、ワーカーの config に付く workerinput を真似た config で確かめる。
"""

from types import SimpleNamespace
from typing import cast

import pytest

from aviutl2_pyrrhulina.pytest_plugin import _fail_if_parallel


def _config(**attributes: object) -> pytest.Config:
    return cast(pytest.Config, SimpleNamespace(**attributes))


def test_not_xdist_worker_is_allowed() -> None:
    _fail_if_parallel(_config())


def test_single_worker_is_allowed() -> None:
    _fail_if_parallel(_config(workerinput={"workerid": "gw0", "workercount": 1}))


def test_multiple_workers_fail() -> None:
    with pytest.raises(pytest.fail.Exception, match="並列"):
        _fail_if_parallel(_config(workerinput={"workerid": "gw0", "workercount": 4}))


def test_unknown_worker_count_fails() -> None:
    # ワーカー数が分からないときは、並列とみなして止める。
    with pytest.raises(pytest.fail.Exception, match="並列"):
        _fail_if_parallel(_config(workerinput={"workerid": "gw0"}))
