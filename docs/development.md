# 開発

このリポジトリ自体を編集する場合の手順です。

## 準備

- [uv](https://docs.astral.sh/uv/)
- g++（MinGW-w64）：検証用プラグインのビルドに使います（`task test` だけなら不要）
- AviUtl2：`task test:e2e` に使います

```shell
uv run task setup     # cloneした直後に1回（submodule の取得と依存関係のインストール）
```

## タスク

| タスク | 内容 |
|---|---|
| `uv run task check` | 静的検査（ruff format / ruff check / ty） |
| `uv run task test` | AviUtl2を起動しないテスト |
| `uv run task test:e2e` | AviUtl2を起動するテスト（先に `build` を実行します） |
| `uv run task build` | 検証用プラグイン（`src/aviutl2_pyrrhulina/_bin/aviutl2_pyrrhulina.aux2`）をビルドする |
| `uv run task clean` | 作業フォルダ `.aviutl2-pyrrhulina/` を消す |

## 構成

| パス | 内容 |
|---|---|
| `src/aviutl2_pyrrhulina/` | Pythonのパッケージ（pytestプラグイン、描画、比較、証跡、サムネイル、配布物の配置） |
| `plugin/agent.cpp` | 検証用プラグイン。ジョブファイルの命令に従ってフレームを描画し（選択中のオブジェクトとしてのプレビュー描画を含む）、結果を書いてAviUtl2を閉じる |
| `plugin/sdk/` | AviUtl2のプラグインSDK（submodule） |
| `tests/` | テスト。`tests/scripts/` は検証用のスクリプト |
| `docs/` | 利用者向けのドキュメント |

## READMEの構成図

READMEの構成図は、手書きのSVG（`docs/images/overview-light.svg` / `overview-dark.svg`）です。2つは `<style>` の色だけが異なり、図を変えるときは両方を同じように直します（`tests/test_readme.py` が食い違いを見つけます）。

PyPIでは相対パスが解決されないため、READMEからは `main` を指す絶対URLで参照しています。PyPIのページは画像を閲覧のたびに読み込むので、過去のバージョンのページにも `main` の図が出ます。

- ファイルを移動・改名・削除しません。過去のバージョンのPyPIページで図が表示されなくなります。
- 過去のバージョンと食い違うほど図を作り直すときは、上書きせず別のファイル名で追加します。

## リリース

`pyproject.toml` の `version` を上げてコミットし、同じ番号のタグをpushします。

```shell
git tag v{バージョン}
git push origin v{バージョン}
```

GitHub Actionsがプラグインをビルドし、wheelとプラグインをReleasesに置きます（`.github/workflows/release.yml`）。
タグと `version` が一致しないときは失敗します。

## AviUtl2 / SDK の更新への追従

AviUtl2は頻繁に更新されます。`plugin/sdk`（submodule）の元の [aviutl2_sdk_mirror](https://github.com/aviutl2/aviutl2_sdk_mirror) は公式の更新からほぼ即時に更新されるので、これを更新の合図にします。

- 対応バージョンは、READMEのバッジ（検証済みのAviUtl2・SDKの日付）にだけ書きます。コードには持たせません。
- 対応バージョンを書き換えるだけならリリースしません。wheelの中身が変わったときだけリリースします。

### 更新が来たときの手順

1. Dependabot が submodule を更新する pull request を作ります。CI（`.github/workflows/ci.yml`）がビルドを確かめます（使っているヘッダ `plugin2.h` / `logger2.h` の破壊的変更はここで見つかります）。
2. 手元のAviUtl2本体を更新し、`uv run task test:e2e` を実行します。
3. 通ったら、同じ pull request でREADMEのバッジ（AviUtl2のバージョン・SDKの日付）を書き換えてマージします。SDKの日付は `plugin/sdk/CHANGELOG.md` の先頭の日付です。
4. `plugin/agent.cpp` かPython側を直したときだけ、パッチリリースします。

| SDK の変更 | 対応 |
|---|---|
| 使っていないヘッダのみ（auf2 など） | マージのみ |
| 使っているヘッダへの追加のみ | マージのみ（新機能を使うなら別途対応） |
| 使っているヘッダの破壊的変更 | `agent.cpp` を修正してパッチリリース |

SDKが変わらなくても、本体の挙動（ログの形式・ini・描画）は変わりうるので、e2eは毎回実行します。
本体だけが更新されてSDKが変わらない回は、Dependabotは反応しません。

### 最低バージョン

最低バージョンは、e2eで実際に確かめた一番古いバージョン（2.1.17）です。理屈で下限を探らず、使うAPIを増やしたときだけ上げます。

- `plugin/agent.cpp` の `kRequiredVersion` が返す値です。本体が満たさないと、AviUtl2がプラグインを読み込みません。
- 本体のバージョン番号は `obj.getinfo("version")` と同じ形式で、2.1.17 は `2011700` です（実測）。
- 本体が満たさないとき、AviUtl2は「version not supported」のダイアログを出して止まります。ピルリナは時間切れで止め、ログからこれを見つけて「AviUtl2 本体が古い」と報告します。
- 上げるときは、`src/aviutl2_pyrrhulina/runner.py` の `MINIMUM_AVIUTL2_VERSION` とREADMEの「前提」も合わせます（`tests/test_runner.py` が食い違いを見つけます）。
- 起動した本体のバージョン番号は、AviUtl2のログ（証跡の `aviutl2.log`）に `host version 2011700` の形で出ます。
