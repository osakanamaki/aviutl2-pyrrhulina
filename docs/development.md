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
| `plugin/agent.cpp` | 検証用プラグイン。ジョブファイルの命令に従ってフレームを描画し、結果を書いてAviUtl2を閉じる |
| `plugin/sdk/` | AviUtl2のプラグインSDK（submodule） |
| `tests/` | テスト。`tests/scripts/` は検証用のスクリプト |
| `docs/` | 利用者向けのドキュメント |

## リリース

`pyproject.toml` の `version` を上げてコミットし、同じ番号のタグをpushします。

```shell
git tag v{バージョン}
git push origin v{バージョン}
```

GitHub Actionsがプラグインをビルドし、wheelとプラグインをReleasesに置きます（`.github/workflows/release.yml`）。
タグと `version` が一致しないときは失敗します。

## AviUtl2 / SDK の更新への追従

（#3 で追加予定）
