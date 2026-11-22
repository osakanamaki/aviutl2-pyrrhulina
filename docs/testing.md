# テストの書き方

[README](../README.md) の最短手順の続きです。

- [プロジェクトを組み立てる](#プロジェクトを組み立てる)
- [描画する](#描画する)
- [ログを検査する](#ログを検査する)
- [全フレームを基準画像と比べる（スナップショット）](#全フレームを基準画像と比べるスナップショット)
- [特定の画像を基準画像と比べる](#特定の画像を基準画像と比べる)
- [描画結果を目で確かめる](#描画結果を目で確かめる)

## プロジェクトを組み立てる

テストでは、AviUtl2のプロジェクト（`.aup2`）をPythonで組み立てます。

```python
from aviutl2_pyrrhulina import Effect, Project, TimelineObject

text = TimelineObject(
    0,  # レイヤー
    0,  # 開始フレーム
    29,  # 終了フレーム
    [
        Effect("テキスト", {"テキスト": "Hello"}),  # オブジェクト
        Effect("my-effect", {"強さ": "50.00"}),  # フィルタ効果
        Effect("標準描画"),  # 描画
    ],
)
project = Project(640, 360, [text])
```

- 効果は、AviUtl2のオブジェクト設定ダイアログと同じ順（オブジェクト → フィルタ効果 → 標準描画）に並べます。
- 効果の名前と項目名・値は、AviUtl2で保存した `.aup2` に書かれているものをそのまま使います。スクリプトの効果の名前は、拡張子を除いたファイル名です（`my-effect.anm2` なら `my-effect`）。
- 省略した項目は、AviUtl2が既定値で補います。
- フレームレートは `Project(..., rate=30, scale=1)` で指定します（`rate / scale` fps）。

### `.aup2` から名前と値を調べる

AviUtl2でオブジェクトを作って保存し、`.aup2` をテキストエディタで開くと、次のように書かれています。

```ini
[0.0]
effect.name=テキスト
テキスト=Hello
[0.1]
effect.name=標準描画
X=0.00
```

`effect.name` の値が `Effect` の名前、その下の行が項目です。

### トラックバーを動かす（中間点）

移動するトラックバーの値は、`.aup2` と同じく「開始,終了,移動方法,設定」の形で書きます。
中間点があるときは `midpoints` にフレーム番号を指定し、値を「開始, 各中間点, 終了」の順に並べます。

```python
square = Effect("my-object", {"サイズ": "20.00,100.00,60.00,直線移動,0"})
obj = TimelineObject(0, 0, 20, [square, Effect("標準描画")], midpoints=[10])
```

## 描画する

```python
result = aviutl2.render(project, frames=[0, 15, 29])
result.images[15]  # Pillow の画像（RGBA）
```

- 1回の呼び出しで、AviUtl2を1回起動し、指定したフレームをすべて描画します。
- 描画の制限時間は60秒です。重いスクリプトは `timeout=120` のように延ばします。
- 描画結果は、透明な部分を含むRGBAの画像です。

画像の中身を直接検査することもできます。

```python
assert result.images[0].getbbox() == (110, 70, 210, 170)  # 描かれた範囲
assert result.images[0].getpixel((160, 120)) == (40, 140, 210, 255)
```

## ログを検査する

スクリプトの `print` は、ログに「`[SCRIPT] [スクリプト名] 本文`」の形で出ます。

```python
assert result.log_lines("[SCRIPT] [my-object] size=100")
```

- プレビュー表示のためにも描画が走るので、同じ行が複数回出ることがあります。回数は当てにしないでください。
- ログ全体は `result.log` で読めます。

### スクリプトのエラー

スクリプトがエラーになっても、AviUtl2は止まらず、何も描画しないだけになります。
見落とさないよう、ログにエラーがあると `render` は `AviUtl2Error` で失敗します。

起きると分かっているエラーは、その行に含まれる文字列を `ignore_log_errors` に渡して除外します。

```python
# 画像ファイルが無いときのエラーだけを除外する（他のエラーでは失敗する）
aviutl2.render(project, [0], ignore_log_errors=["ImageService::canLoadFile"])
```

エラーになること自体を検査するときは、`pytest.raises` を使います。

```python
with pytest.raises(AviUtl2Error, match="script exception"):
    aviutl2.render(project, [0])
```

## 全フレームを基準画像と比べる（スナップショット）

`assert_snapshot` は、描画した全フレームを、テスト名から自動で決まる基準画像と比べます。
一度目で確かめた描画結果を正解として残し、スクリプトを変えた前後のデグレを見つけるのに使います。

```python
def test_my_object(aviutl2):
    result = aviutl2.render(project, frames=[0, 5, 10])
    aviutl2.assert_snapshot(result)  # 3フレームとも基準画像と比べる
```

- 基準画像は `<テストファイルのフォルダ>/baselines/<テストファイル名>/<テスト名>/frame_00005.png` に置かれます。場所は `aviutl2_baselines` fixture を上書きすると変えられます。
- 一致しないフレームがあっても途中で止めず、一致しなかったフレームをまとめて報告します。
- 1つのテストで何度も描画して比べるときは、`assert_snapshot(result, name="after_move")` のように名前を付けて区別します（`<テスト名>/after_move/` の下に置かれます）。
- 少しの違いを許すときは `tolerance` に、各画素・各チャンネルで許す差（0〜255）を指定します。
- 完全に透明な画素は、色が違っていても同じとみなします。

### 基準画像を書き込む

基準画像は自動では作りません。描画結果を[目で確かめて](#描画結果を目で確かめる)から書き込みます。

```shell
pytest --aviutl2-update-baselines                       # 実行したテストすべて
pytest -k test_my_object --aviutl2-update-baselines     # 確かめたテストだけ
```

- テストの名前を変えたり消したりしても、古い基準画像は自動では消えません。
- AviUtl2本体を更新すると、スクリプトを変えていなくても描画結果が変わり、一致しなくなることがあります。

## 特定の画像を基準画像と比べる

比べる画像と基準画像のパスを自分で決めたいとき（特定のフレームだけ比べる、複数のテストで同じ基準画像を使うなど）は、`assert_matches` を使います。

```python
from pathlib import Path

BASELINES = Path(__file__).parent / "baselines"


def test_last_frame(aviutl2):
    result = aviutl2.render(project, frames=[29])
    aviutl2.assert_matches(result.images[29], BASELINES / "last_frame.png")
```

基準画像の書き込み（`--aviutl2-update-baselines`）と `tolerance` は、`assert_snapshot` と同じです。

## 描画結果を目で確かめる

テストが終わると、`.aviutl2-pyrrhulina/evidence/index.html` ができます（パスはpytestの結果の最後に表示されます）。
ブラウザで開くと、今回実行したテストの描画結果を一覧できます。pytestの検査では判定しにくい絵柄の確認に使います。

- 失敗したテストが先頭に並びます。
- 基準画像と比べたテストは、一致したときも「基準画像／今回／差分」を並べて表示します。差分は、許容を超えた画素が白になります。
- 透明な部分は市松模様で表示されます。
- 2フレーム以上描画したテストは、動きを見られるようアニメーション（`frames.webp`）も表示します。フレーム番号の間隔どおりの時間で再生します。
- 載るのは今回実行したテストだけです。`-k` などで実行しなかったテストの古い証跡は載りません。

テストごとの証跡（描画したフレーム・使ったプロジェクト・AviUtl2のログ・差分）は、テストの成否に関係なく `.aviutl2-pyrrhulina/evidence/<テスト名>/` に残ります。
1つのテストで何度も描画したときは、最後の描画結果が残ります。

## AviUtl2を起動するテストだけを除く

AviUtl2を起動するテスト（`aviutl2` fixture を使うテスト）には、`aviutl2` マーカーが自動で付きます。

```shell
pytest -m "not aviutl2"   # AviUtl2を起動しないテストだけ
pytest -m aviutl2         # AviUtl2を起動するテストだけ
```
