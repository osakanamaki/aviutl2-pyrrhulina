# リファレンス

- [pytest のオプションと環境変数](#pytest-のオプションと環境変数)
- [fixture](#fixture)
- [`aviutl2` fixture のメソッド](#aviutl2-fixture-のメソッド)
- [プロジェクトの組み立て](#プロジェクトの組み立て)
- [`RenderResult`](#renderresult)
- [例外](#例外)
- [pytest を使わずに使う](#pytest-を使わずに使う)
- [作業フォルダ](#作業フォルダ)
- [困ったとき](#困ったとき)

## pytest のオプションと環境変数

| オプション | 説明 |
|---|---|
| `--aviutl2-app <フォルダ>` | 複製元のAviUtl2のフォルダ。既定は環境変数 `AVIUTL2_APP`、無ければ `C:\Program Files\AviUtl2` |
| `--aviutl2-update-baselines` | 比較せずに、今回の描画結果で基準画像を書き換える |

| マーカー | 説明 |
|---|---|
| `aviutl2` | AviUtl2を起動するテスト。`aviutl2` fixture を使うテストに自動で付く |

## fixture

利用側の `conftest.py` で上書きして使います。

| fixture | スコープ | 説明 |
|---|---|---|
| `aviutl2_scripts` | session | AviUtl2の `Script` フォルダの下に置くフォルダ名と、その中身にするフォルダの辞書。既定は空 |
| `aviutl2_plugins` | session | AviUtl2の `Plugin` フォルダに置くファイルかフォルダの並び。既定は空（[プラグインと配布物の検査](package.md)） |
| `aviutl2_package` | session | 配布物とインストール手順（`Package`）。指定すると手順どおりに置いてから検査する。既定は `None` |
| `aviutl2_baselines` | function | `assert_snapshot` の基準画像を置くフォルダ。既定はテストファイルと同じ場所の `baselines` |
| `aviutl2_environment` | session | 検証用の環境（`Environment`）。テストのセッションごとに1回作り直す |
| `aviutl2` | function | テストから使う入口（下記） |

## `aviutl2` fixture のメソッド

### `render(project, frames, *, timeout=60, allow_log_errors=False, ignore_log_errors=())`

`project` をAviUtl2で開き、`frames` の各フレームを描画して `RenderResult` を返します。

| 引数 | 説明 |
|---|---|
| `project` | `Project` |
| `frames` | 描画するフレーム番号の並び |
| `timeout` | 制限時間（秒）。超えるとAviUtl2を止めて `AviUtl2Error` |
| `allow_log_errors` | `True` なら、ログにエラーがあっても例外にしない |
| `ignore_log_errors` | 例外にしないエラー行に含まれる文字列の並び |

### `assert_snapshot(result, *, name="", tolerance=0)`

`result` の全フレームを、テスト名から決まる基準画像と比べます。一致しないと `ImageMismatch`。
同じテストで同じ `name` を2回使ったり、`name` にファイル名に使えない文字が含まれたりすると `ValueError` になります。

### `assert_matches(actual, baseline_path, *, tolerance=0)`

画像 `actual` を `baseline_path` の基準画像と比べます。一致しないと `ImageMismatch`。

## プロジェクトの組み立て

| クラス | 引数 |
|---|---|
| `Project(width, height, objects, rate=30, scale=1, audio_rate=44100, version=2011700)` | フレームレートは `rate / scale` fps。`version` はプロジェクトファイルに書く本体のバージョン番号 |
| `TimelineObject(layer, start, end, effects, midpoints=())` | 1フレームだけのオブジェクトは `start == end`。`midpoints` は中間点のフレーム番号 |
| `Effect(name, params={})` | 効果の名前と、項目名→値の辞書。値は `.aup2` に書かれている形 |

## `RenderResult`

| 属性・メソッド | 説明 |
|---|---|
| `images` | フレーム番号 → 描画結果（Pillow の RGBA 画像） |
| `image_paths` | フレーム番号 → 証跡として保存したPNGのパス |
| `log` | 今回の起動でAviUtl2が出したログ全体 |
| `log_lines(containing)` | `containing` を含むログの行 |
| `log_errors` | エラーを示すログの行（`[ERROR]` と、Luaの実行時エラー `script exception`） |

## 例外

| 例外 | 起きるとき |
|---|---|
| `AviUtl2Error` | 描画できなかったとき（時間切れ、フレームが範囲外、ログにエラーがある、など） |
| `ImageMismatch` | 基準画像が無い、または一致しないとき（`AssertionError` の一種） |
| `PackageError` | 配布物をインストール手順どおりに置けないとき |

## pytest を使わずに使う

`create_environment` と `render` は、pytestを使わずに呼べます。

```python
from pathlib import Path

from aviutl2_pyrrhulina import create_environment, render

environment = create_environment(
    Path(".aviutl2-pyrrhulina/app"),  # 検証用の環境を作るフォルダ
    Path(r"C:\Program Files\AviUtl2"),  # 複製元の AviUtl2
    {"my-script-dev": Path("script")},  # Script フォルダの下に置くもの
)
work_dir = Path("work")  # プロジェクト・描画結果・ログを置くフォルダ
work_dir.mkdir(exist_ok=True)
project.write(work_dir / "project.aup2")
result = render(environment, work_dir / "project.aup2", [0, 9], work_dir)
```

基準画像との比較は `compare_images`（比較結果を返す）と `assert_images_match`（一致しないと例外）で行えます。

## 作業フォルダ

ピルリナは、pytestを実行したフォルダ（rootdir）の `.aviutl2-pyrrhulina/` を作業フォルダにします。
すべて作り直せるものなので、Gitでは管理せず、いつ消しても構いません。

```text
.aviutl2-pyrrhulina/
├─ app/                  検証用の環境（AviUtl2の複製）。data フォルダはセッションごとに作り直す
├─ package-tmp/          配布物を展開する一時フォルダ（{tmp}）
├─ evidence/
│  ├─ index.html         証跡の一覧
│  └─ <テスト名>/         テストごとの証跡（テストを始めるときに消して作り直す）
│     ├─ project.aup2    使ったプロジェクト
│     ├─ aviutl2.log     AviUtl2のログ
│     ├─ frame_00000.png 描画したフレーム
│     ├─ frames.webp     描画したフレームのアニメーション
│     └─ ...             基準画像と比べたときの今回の画像（*.actual.png）と差分（*.diff.png）
└─ thumbnail/            動くサムネイルを作るときの途中のファイル
```

検証用の環境では、`app/` に `data` フォルダを作ることで、AviUtl2の設定の保存先を普段の `C:\ProgramData\aviutl2` から切り替えています。
また、配置したプラグインとスクリプトを信頼済みとして登録し、初回起動時の確認ダイアログが出ないようにしています。

## 困ったとき

### テストがスキップされる（「AviUtl2 が見つかりません」）

AviUtl2が `C:\Program Files\AviUtl2` 以外にあります。環境変数 `AVIUTL2_APP` か `--aviutl2-app` でフォルダを指定します。

### 「ログにエラーがあります」で失敗する

スクリプトの実行時エラーなどが、AviUtl2のログに出ています。エラーの行と、ログのパス（証跡フォルダの `aviutl2.log`）が表示されるので、内容を確認します。
起きると分かっているエラーは `ignore_log_errors` で除外できます（[テストの書き方](testing.md#スクリプトのエラー)）。

### 時間切れになる（「rendering timeout」「秒以内に終了しなかった」）

描画が重いか、スクリプトが終わらなくなっています。重いだけなら `render(..., timeout=120)` のように制限時間を延ばします。
どの手順で止まったかがエラーに表示されます。

### 「AviUtl2 本体が古いため」と表示される

AviUtl2が、ピルリナの最低バージョン（README の「前提」）より古いです。AviUtl2を更新します。

### 「rendering_scene_video failed」で失敗する

描画するフレーム番号が、プロジェクトの範囲（オブジェクトの終了フレーム）を超えている可能性があります。

### 「検証用の環境を消せませんでした」

前回の検証用のAviUtl2が起動したままになっています。タスクマネージャーで `.aviutl2-pyrrhulina\app\aviutl2.exe` を終了させます。

### AviUtl2のダイアログが出て止まる

`Plugin`・`Script` フォルダの直下と一つ下のフォルダにあるプラグインとスクリプトは、信頼済みとして登録されるので確認ダイアログは出ません。
それより深い場所に置いたファイルは登録されないため、ダイアログが出て止まることがあります（AviUtl2もそこまでは読みません）。止まったときは制限時間で終了し、失敗として報告されます。

### `index.html` ができない

AviUtl2を起動するテスト（`aviutl2` fixture を使うテスト）を1つも実行していないと作られません。
