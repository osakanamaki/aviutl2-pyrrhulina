# プラグインと配布物の検査

スクリプトのほか、プラグイン（`.auf2` など）も検証用の環境に置いて検査できます。
[AviUtl2 Catalog](https://github.com/Neosku/aviutl2-catalog) に掲載する配布物（zip）を、インストール手順どおりに置いてから検査することもできます。

- [プラグインを置く](#プラグインを置く)
- [配布物をインストール手順どおりに置いて検査する](#配布物をインストール手順どおりに置いて検査する)
- [カタログに登録するハッシュ値（XXH3_128）を出す](#カタログに登録するハッシュ値xxh3_128を出す)

## プラグインを置く

`conftest.py` の `aviutl2_plugins` で、`Plugin` フォルダに置くファイルかフォルダを指定します。

```python
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def aviutl2_plugins():
    return [Path(__file__).parent.parent / "build" / "my-filter.auf2"]
```

- フォルダを指定すると、その名前のまま `Plugin` フォルダの下に置きます。AviUtl2が読むのは、`Plugin` フォルダの直下と一つ下のフォルダまでです。
- 置いたプラグインとスクリプトは、信頼済みとして登録します（初回起動時の確認ダイアログが出ないようにするため）。

## 配布物をインストール手順どおりに置いて検査する

カタログは、登録時にアプリで実際にインストールを試しますが、「インストールした状態でAviUtl2上でちゃんと動くか」までは確かめません。
`aviutl2_package` で配布物とインストール手順を指定すると、手順どおりに置いた環境で、今あるテストをそのまま実行できます。

```python
from pathlib import Path

import pytest
from aviutl2_pyrrhulina import Package

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def aviutl2_package():
    return Package.from_json(ROOT / "dist" / "my-package.zip", ROOT / "install.json")
```

インストール手順（`install.json`）は、カタログのデータ（`index.json` の `installer.install`）と同じ形で書きます。

```json
[
  {"action": "download"},
  {"action": "extract"},
  {"action": "copy", "from": "{tmp}/MyPackage/my-filter.auf2", "to": "{pluginsDir}"},
  {"action": "copy", "from": "{tmp}/MyPackage/Script", "to": "{scriptsDir}/MyPackage"}
]
```

カタログのデータと同じ `{"install": [...]}` や `{"installer": {"install": [...]}}` の形でも読めます。

| 手順 | 動き |
|---|---|
| `download` | ネットワークから取得する代わりに、手元の配布物を一時フォルダに置きます（以降 `{download}` で参照できます） |
| `extract` | zipを展開します。`from` の既定は `{download}`、`to` の既定は `{tmp}` |
| `copy` | ファイルは `to` のフォルダの中へ、フォルダは中身を `to` のフォルダの中へコピーします。コピーするものが無いと失敗します |
| `delete` | `path` を消します |
| `run`・`extractSfx`・`runAuoSetup` | 外部のプログラムを実行するため、対応していません（失敗します） |

| マクロ | 検証用の環境での場所 |
|---|---|
| `{tmp}` | 一時フォルダ（`.aviutl2-pyrrhulina/package-tmp`） |
| `{appDir}` | AviUtl2本体のフォルダ（`.aviutl2-pyrrhulina/app`） |
| `{dataDir}` | `{appDir}/data` |
| `{pluginsDir}` | `{dataDir}/Plugin` |
| `{scriptsDir}` | `{dataDir}/Script` |
| `{download}` | `download` で置いた配布物 |

- 置き場所に指定できるのは、検証用の環境の中だけです。外を指すと失敗します。
- `aviutl2_scripts`・`aviutl2_plugins` と一緒に使うこともできます。

## カタログに登録するハッシュ値（XXH3_128）を出す

配布物から置いたファイルのハッシュ値を、カタログのデータ（`version.file`）と同じ形で出します。登録フォームへの書き写しや、値が合っているかの確認に使います。

`aviutl2_package` を指定してテストを実行すると、pytestの結果の最後に表示されます。

```text
配布物から置いたファイル（カタログの version.file と同じ形）:
[
  {
    "path": "{pluginsDir}/my-filter.auf2",
    "XXH3_128": "98b26138fd3dd64ecbdebc178f24aac6"
  }
]
```

AviUtl2を起動せずに、コマンドで出すこともできます。

```shell
uv run aviutl2-pyrrhulina-package dist/my-package.zip install.json
```
