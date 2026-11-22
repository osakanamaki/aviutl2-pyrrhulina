# 動くサムネイル

AviUtl2で描画した結果から、[AviUtl2 Catalog](https://github.com/Neosku/aviutl2-catalog) 用の動くサムネイル（アニメーションWebP/GIF）を作ります。
テストではないので、pytestを使わずにコマンドで実行します。プロジェクトはAviUtl2で保存した `.aup2` を使います。

```shell
# uv で追加した場合
uv run aviutl2-pyrrhulina-thumbnail demo.aup2 thumbnail.webp --script my-script-dev=script

# pip で追加した場合（仮想環境を有効にしてから）
aviutl2-pyrrhulina-thumbnail demo.aup2 thumbnail.webp --script my-script-dev=script
```

`--script` は、AviUtl2の `Script` フォルダの下に置くフォルダ名と、その中身にするフォルダです（pytestの `aviutl2_scripts` と同じ）。複数指定できます。

## 指定できる項目

| 項目 | 指定 | 既定 |
|---|---|---|
| 形式 | 出力ファイルの拡張子（`.webp` / `.gif`） | - |
| 大きさ | `--size`。縦横比を保って縮小し、正方形の中央に置きます | 206（カタログの推奨） |
| 長さ | `--seconds`。10秒まで | 3秒 |
| fps | `--fps`。プロジェクトのフレームレートを割り切れる値だけ（30fpsのプロジェクトなら 30・15・10 など） | 30 |
| 開始フレーム | `--start` | 0 |
| 背景 | `--background`（例: `#000000`） | 透明 |
| 画質 | `--quality`（WebPのみ、0〜100） | 80 |
| AviUtl2のフォルダ | `--app` | 環境変数 `AVIUTL2_APP`、無ければ `C:\Program Files\AviUtl2` |
| 作業フォルダ | `--work-dir` | `.aviutl2-pyrrhulina` |

## 注意

- 細い線をきれいに残すため、プロジェクトは大きめの解像度で作って縮小させるのがおすすめです。
- 10MBを超えると警告が出ます。fps・長さ・画質を下げると小さくなります。
- GIFは透明を2段階（透明か不透明か）でしか表せず、半透明の部分は不透明になります。GIFでは `--background` の指定をおすすめします。
- GIFの表示時間は10ミリ秒単位なので、30fpsはわずかに速く再生されます。

## Pythonから使う

```python
from pathlib import Path

from aviutl2_pyrrhulina import create_environment, make_thumbnail

environment = create_environment(
    Path(".aviutl2-pyrrhulina/app"), Path(r"C:\Program Files\AviUtl2"), {"my-script-dev": Path("script")}
)
make_thumbnail(environment, Path("demo.aup2"), Path("thumbnail.webp"), seconds=3, fps=30)
```

`project` には `.aup2` のパスのほか、テストと同じく `Project` も渡せます。
