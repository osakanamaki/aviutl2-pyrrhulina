# aviutl2-pyrrhulina

AviUtl2 のスクリプトを実際の AviUtl2 で動かし、描画結果とログを pytest から確かめるための道具です。
人が AviUtl2 を開いて 1 つずつ試していた確認を、コマンド 1 つで再現できるようにします。

普段使っている AviUtl2 の設定やプロジェクトには触れません（検証専用の複製を作って動かします）。

## 前提と制限

- Windows、AviUtl2 がインストール済みであること（2.1.17 で確認）
- 検証用プラグインのビルドに g++（MinGW-w64）が必要
- AviUtl2 のウィンドウが一瞬表示されます。画面のない環境では動きません
- テストの並列実行（pytest-xdist）には対応していません。検証用の環境を 1 つしか作らないためです

## 準備

```
uv run task setup
```

プラグインの実行ファイルは git に入れていません。
そのため、他のリポジトリから使うときは、ビルド済みのこのフォルダをパスで参照します。

```
uv add --dev --editable ../aviutl2-pyrrhulina
```

利用側のリポジトリでは、`.gitignore` に次の行を追加してください。
検証用の AviUtl2 の複製と、テストごとの証拠ファイルがここに作られます。

```
.aviutl2-pyrrhulina/
```

## テストの書き方

`conftest.py` で、検証するスクリプトのフォルダを指定します。

```python
@pytest.fixture(scope="session")
def aviutl2_scripts():
    return {"my-script-dev": Path(__file__).parent.parent / "script"}
```

テストでは、プロジェクトを組み立てて描画させます。
効果の名前と項目は、AviUtl2 で保存した `.aup2` に書かれているものをそのまま使います。

```python
def test_draws_bar(aviutl2):
    effect = Effect("連番まとめ", {"フレーム位置": "5"})
    project = Project(640, 360, [TimelineObject(0, 0, 10, [Effect("テキスト"), Effect("標準描画"), effect])])

    result = aviutl2.render(project, frames=[5])

    assert result.log_lines("[SCRIPT]")
    aviutl2.assert_matches(result.images[5], BASELINES / "bar_5.png")
```

- 基準画像が無い、または一致しないときは失敗し、今回の画像と差分を `.aviutl2-pyrrhulina/evidence/<テスト名>/` に残します。同じ場所に、使ったプロジェクトと AviUtl2 のログも残ります。
- 基準画像は自動では作りません。画像を目で確認してから `pytest --aviutl2-update-baselines` で書き込みます。
- AviUtl2 を起動するテストには `aviutl2` マーカーが自動で付きます（`pytest -m "not aviutl2"` で除外）。
