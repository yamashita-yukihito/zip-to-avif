# zip-to-avif

アーカイブ（ZIP/RAR/7z）や画像フォルダ内の画像をAVIF/WebPに変換して軽量化するツール群。
単体ファイル変換とディレクトリ一括変換に対応。

## ツール一覧

| ファイル | 用途 |
|---------|------|
| `zip_to_avif.bat` | アーカイブ → AVIF変換（D&D用） |
| `zip_to_avif_dir.bat` | ディレクトリ一括AVIF変換（D&D用） |
| `zip_to_webp.bat` | アーカイブ → WebP変換（D&D用） |
| `zip_to_webp_dir.bat` | ディレクトリ一括WebP変換（D&D用） |
| `zip_to_avif.py` | AVIF変換 CPU版（Pillow） |
| `zip_to_avif_gpu.py` | AVIF変換 GPU版（NVENC av1） |
| `zip_to_avif_dir.py` | ディレクトリ一括AVIF変換 |
| `zip_to_webp.py` | WebP変換（libwebp, CPU） |
| `zip_to_webp_dir.py` | ディレクトリ一括WebP変換 |

### AVIF vs WebP

| | AVIF (GPU) | WebP |
|--|-----------|------|
| エンコーダ | av1_nvenc (GPU) | libwebp (CPU) |
| 速度 | 速い | そこそこ速い |
| 圧縮率 | 画像による（軽いJPGだと逆に大きくなることあり） | 安定して小さくなる |
| 色空間 | nvencがyuv420pを無視する場合あり | yuv420p確実 |

軽いJPGが多い場合はWebP版の方が確実に小さくなる。

---

## Windows（batファイル）での使い方

### 単体変換

`zip_to_avif.bat` または `zip_to_webp.bat` にアーカイブファイルをドラッグ＆ドロップ。

- 出力: `元ファイル名_avif.zip` / `元ファイル名_webp.zip`
- 対応形式: zip, rar, 7z, cbz, cbr

### ディレクトリ一括変換

`zip_to_avif_dir.bat` または `zip_to_webp_dir.bat` にフォルダをドラッグ＆ドロップ。

フォルダ内のアーカイブと画像フォルダを自動検出し、一覧表示:

```
  [  1] short_manga.zip                    12MB  JPG 100%     -> compress
  [  2] photo_folder/                     120MB  PNG 80%      -> compress (350img)
  [  3] huge_archive.zip                  890MB  JPG 100%     -> compress

Select (e.g. 1,2 / all / r=rescan / q):
```

- 番号で選択（`1,3` / `1-5` / `all`）
- 変換完了後に自動再スキャンしてループ（続けて次を選べる）
- `r` で手動再スキャン、`q` で終了
- avif/webpが50%以上のものはリストに表示しない（変換不要）
- サイズ昇順ソート（一番下が一番重い）

#### フォルダ内の画像変換

アーカイブだけでなく、JPG/PNGが入ったフォルダも検出して変換できる。
フォルダの場合は画像を直接AVIF/WebPに変換し、元ファイルを置き換える。
変換後にサイズが大きくなった画像は元のまま残す。

### 前提条件

- WSL2 + Ubuntu
- Python3, ffmpeg, p7zip-full, unar

```bash
sudo apt install ffmpeg p7zip-full unar
cp zip_to_avif.py zip_to_avif_gpu.py zip_to_avif_dir.py ~/bin/
cp zip_to_webp.py zip_to_webp_dir.py ~/bin/
```

AVIF GPU版はRTX 40系以降 + Windows側にNVIDIAドライバが必要。

---

## コマンドライン

### 単体アーカイブ変換

```bash
# AVIF CPU版
python3 zip_to_avif.py <入力> <出力ZIP> <品質> [最大辺px]

# AVIF GPU版
python3 zip_to_avif_gpu.py <入力> <出力ZIP> <品質> [並列数] [最大辺px]

# WebP版
python3 zip_to_webp.py <入力> <出力ZIP> <品質> [並列数] [最大辺px]
```

### ディレクトリ一括変換

```bash
# AVIF版
python3 zip_to_avif_dir.py <ディレクトリ> [品質] [並列数] [最大辺px]

# WebP版
python3 zip_to_webp_dir.py <ディレクトリ> [品質] [並列数] [最大辺px]
```

### 例

```bash
# 単体: 品質75でWebP変換
python3 zip_to_webp.py input.zip output.zip 75

# ディレクトリ一括: 品質75、並列4、長辺2000px以内
python3 zip_to_webp_dir.py /path/to/dir 75 4 2000
```

---

## 品質の目安

| 品質 | 説明 |
|------|------|
| 60 | 最大圧縮。サイズ最優先 |
| 75 | バランス良好（推奨） |
| 85 | 高画質維持 |

## 備考

- 画像以外のファイルはそのまま維持される
- 出力ZIPは無圧縮（AVIF/WebP自体が圧縮済みのため）
- 変換エラーが発生したファイルは元のまま保持される
- 変換後にサイズが大きくなった画像は元を採用（逆効果防止）
- 20ファイルごとに進捗・圧縮率・ETA表示
