# zip-to-avif

アーカイブ（ZIP/RAR/7z）内の画像をAVIFに変換して軽量なZIPとして出力するツール。
CPU版とGPU版の2種類あり。長辺が指定pxを超える画像は自動で縮小する。

## Windows（batファイル）での使い方

`zip_to_avif.bat` にアーカイブファイルをドラッグ＆ドロップするだけ。
WSL2のUbuntu上で処理が実行される。

- 品質: 75、最大辺: 3000px（変更したい場合はbatファイル内の数値を編集）
- 出力: 元ファイル名に `_avif` を付けたZIP（例: `manga.rar` → `manga_avif.zip`）
- 対応形式: zip, rar, 7z, cbz, cbr

### 前提条件

- WSL2 + Ubuntu
- Ubuntu側に以下がインストール済み:
  - Python3, ffmpeg, p7zip-full, unar
  - スクリプトが `~/bin/` に配置済み

```bash
sudo apt install ffmpeg p7zip-full unar
cp zip_to_avif.py zip_to_avif_gpu.py ~/bin/
```

---

## CPU版: zip_to_avif.py

Pillow + pillow-avif-plugin を使用。ZIP/RAR/7z/CBZ/CBR対応。

### 必要なもの

```bash
pip install Pillow pillow-avif-plugin
sudo apt install p7zip-full unar
```

### 使い方

```bash
python3 zip_to_avif.py <入力アーカイブ> <出力ZIP> <品質> [最大辺px]
```

### 例

```bash
# 品質75、長辺3000px以内（デフォルト）
python3 zip_to_avif.py input.zip output.zip 75

# 品質75、長辺2000px以内
python3 zip_to_avif.py input.zip output.zip 75 2000

# リサイズなし
python3 zip_to_avif.py input.zip output.zip 75 0
```

---

## GPU版: zip_to_avif_gpu.py

NVIDIA GPUのAV1ハードウェアエンコーダ（NVENC）を使用。RTX 40系以降対応。
CPU版より大幅に高速。ZIP/RAR/7z/CBZ/CBR対応。

### 必要なもの

```bash
sudo apt install ffmpeg p7zip-full unar
```

※ WSL2の場合、NVIDIAドライバがWindows側にインストール済みであること。

### 使い方

```bash
python3 zip_to_avif_gpu.py <入力アーカイブ> <出力ZIP> <品質> [並列数] [最大辺px]
```

### 例

```bash
# 品質75、並列4、長辺3000px以内（すべてデフォルト）
python3 zip_to_avif_gpu.py input.zip output.zip 75

# RAR入力
python3 zip_to_avif_gpu.py input.rar output.zip 75

# 品質85、並列6、長辺2000px以内
python3 zip_to_avif_gpu.py input.zip output.zip 85 6 2000

# リサイズなし
python3 zip_to_avif_gpu.py input.zip output.zip 75 4 0
```

---

## 引数一覧

| 引数 | CPU版 | GPU版 | 説明 |
|------|-------|-------|------|
| 入力 | 1番目 | 1番目 | 変換元のアーカイブパス |
| 出力 | 2番目 | 2番目 | 出力先のZIPファイルパス |
| 品質 | 3番目 | 3番目 | AVIF品質（1-100）。75推奨 |
| 並列数 | - | 4番目 | GPU並列数（デフォルト4） |
| 最大辺px | 4番目 | 5番目 | 長辺の最大px（デフォルト3000、0で無効） |

## 品質の目安

| 品質 | 説明 |
|------|------|
| 60 | 最大圧縮。サイズ最優先。多少の劣化あり |
| 75 | バランス良好（推奨）。漫画でも十分な画質 |
| 85 | 高画質維持。元の20-30%程度のサイズ |

## 備考

- 画像以外のファイルはそのまま維持される
- 出力ZIPは無圧縮（AVIF自体が圧縮済みのため）
- 変換エラーが発生したファイルは元のまま保持される
- 20ファイルごとに進捗・ETA表示
- リサイズは縦横比を維持したまま長辺を指定px以内に縮小
