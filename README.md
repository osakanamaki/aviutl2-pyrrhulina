# 🐠ピルリナ（aviutl2-pyrrhulina）

pytestを用いてAviUtl2のスクリプトを実際に動かし、描画結果とログを検証するためのツールです。

検証専用の環境を作成します。既存プロジェクトには触れません。

```mermaid
flowchart LR
    subgraph User["利用者が用意するもの"]
        direction TB
        Script["AviUtl2スクリプト<br/>(テスト対象)"] ~~~ TestCode["テストコード<br/>(conftest.py / test_*.py)"] ~~~ Baseline["基準画像<br/>(baselines/)"]
    end

    subgraph Runner["テスト実行・描画"]
        Pytest(["pytest"])
        Pyrrhulina["🐠ピルリナ<br/>(検証専用環境)"]
        AviUtl2["AviUtl2"]
    end

    subgraph Output["出力・結果"]
        Result["証跡<br>（画像・ログ・失敗時差分）"]
    end

    User -- 実行・比較 --> Pytest
    Pytest -- 呼出 --> Pyrrhulina
    Pyrrhulina -- 起動・描画 --> AviUtl2
    AviUtl2 -- 画像・ログ --> Pyrrhulina
    Pyrrhulina -- 保存 --> Result
    Result -- 検証 --> Pytest
    Pytest -. 基準画像更新<br>（--aviutl2-update-baselines） .-> User
```

## 前提

- Windows、AviUtl2(2.1.17)
- Python 3.12 以上
- テストの並列実行（pytest-xdist）: 未対応
- 検証は、実際にAviUtl2のウィンドウが一瞬表示されます。画面のない環境では動きません。

## 本ツールの利用

### 準備

[Releases](https://github.com/osakanamaki/aviutl2-pyrrhulina/releases)のwheelを追加します。

- 追加の例（どちらか1回）
  - `pip install https://github.com/osakanamaki/aviutl2-pyrrhulina/releases/download/v{バージョン}/aviutl2_pyrrhulina-{バージョン}-py3-none-any.whl`
  - `uv add --dev https://github.com/osakanamaki/aviutl2-pyrrhulina/releases/download/v{バージョン}/aviutl2_pyrrhulina-{バージョン}-py3-none-any.whl`
- Gitによるバージョン管理をしている場合、以下のフォルダを`.gitignore`します。
  - `.aviutl2-pyrrhulina/`

### テストの書き方

`conftest.py` で、検証するスクリプトのフォルダを指定します。

```python
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def aviutl2_scripts():
    return {"my-script-dev": Path(__file__).parent.parent / "script"}
```

テストでは、プロジェクトを組み立てて描画させます。
効果の名前と項目は、AviUtl2で保存した `.aup2` に書かれているものをそのまま使います。

```python
from pathlib import Path

from aviutl2_pyrrhulina import Effect, Project, TimelineObject

BASELINES = Path(__file__).parent / "baselines"  # 基準画像を置くフォルダ


def test_draws_bar(aviutl2):
    effect = Effect("連番まとめ", {"フレーム位置": "5"})
    project = Project(640, 360, [TimelineObject(0, 0, 10, [Effect("テキスト"), Effect("標準描画"), effect])])

    result = aviutl2.render(project, frames=[5])

    assert result.log_lines("[SCRIPT]")
    aviutl2.assert_matches(result.images[5], BASELINES / "bar_5.png")
```

- 基準画像が無い、または一致しないときは失敗し、今回の画像と差分を `.aviutl2-pyrrhulina/evidence/<テスト名>/` に残します。同じ場所に、使ったプロジェクトとAviUtl2のログも残ります。
- 基準画像は自動では作りません。画像を目で確認してから `pytest --aviutl2-update-baselines` で書き込みます。
- AviUtl2を起動するテストには `aviutl2` マーカーが自動で付きます（`pytest -m "not aviutl2"` で除外）。

## 本ツールの開発

このリポジトリ自体を編集する場合

```shell
uv run task setup     # cloneした直後に1回
uv run task test      # AviUtl2を起動しないテスト
uv run task test:e2e  # AviUtl2を起動するテスト※
```

### ※追加の前提

`task test:e2e` は、検証用プラグイン（`src/aviutl2_pyrrhulina/_bin/aviutl2_pyrrhulina.aux2`）を先にビルドします。
ビルドにはg++（MinGW-w64）が必要です（`task test`のみの利用であればビルド不要）。

### リリース

`pyproject.toml` の `version` を上げてコミットし、同じ番号のタグをpushします。

```shell
git tag v{バージョン}
git push origin v{バージョン}
```

GitHub Actionsがプラグインをビルドし、wheelとプラグインをReleasesに置きます（`.github/workflows/release.yml`）。
タグと `version` が一致しないときは失敗します。
