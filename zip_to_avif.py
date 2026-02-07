import zipfile
import os
import sys
import io
import subprocess
import tempfile
import time
from pathlib import Path

import pillow_avif
from PIL import Image

IMAGE_EXTS = {'jpg', 'jpeg', 'png', 'webp', 'bmp'}
ARCHIVE_EXTS = {'zip', 'rar', '7z', 'cbz', 'cbr'}


def extract_archive(src, dest_dir):
    """アーカイブを展開（zip/rar/7z対応）"""
    ext = src.rsplit('.', 1)[-1].lower() if '.' in src else ''
    if ext in ('zip', 'cbz'):
        with zipfile.ZipFile(src, 'r') as zin:
            zin.extractall(dest_dir)
    elif ext in ('rar', 'cbr'):
        subprocess.run(['unar', '-no-directory', '-o', dest_dir, src],
                       capture_output=True, check=True)
    elif ext == '7z':
        subprocess.run(['7z', 'x', f'-o{dest_dir}', '-y', src],
                       capture_output=True, check=True)
    else:
        raise ValueError(f"未対応の形式: .{ext}")


if len(sys.argv) < 4:
    print("Usage: python3 zip_to_avif.py <入力アーカイブ> <出力ZIP> <品質(1-100)> [最大辺px]")
    print("  対応形式: zip, rar, 7z, cbz, cbr")
    print("  品質の目安: 60=最大圧縮, 75=推奨, 85=高画質")
    print("  最大辺: 長辺がこのpxを超える画像を縮小（デフォルト3000、0で無効）")
    sys.exit(1)

SRC = sys.argv[1]
DST = sys.argv[2]
QUALITY = int(sys.argv[3])
MAX_SIZE = int(sys.argv[4]) if len(sys.argv) > 4 else 3000

if not os.path.isfile(SRC):
    print(f"エラー: ファイルが見つかりません: {SRC}")
    sys.exit(1)

ext = SRC.rsplit('.', 1)[-1].lower() if '.' in SRC else ''
if ext not in ARCHIVE_EXTS:
    print(f"エラー: 未対応の形式です (.{ext})")
    print(f"  対応形式: {', '.join(sorted(ARCHIVE_EXTS))}")
    sys.exit(1)

start = time.time()

with tempfile.TemporaryDirectory() as tmpdir:
    in_dir = os.path.join(tmpdir, 'in')
    os.makedirs(in_dir)

    # アーカイブを展開
    print("Extracting archive...", flush=True)
    extract_archive(SRC, in_dir)

    # 展開されたファイルを走査
    all_files = []
    for root, dirs, files in os.walk(in_dir):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, in_dir)
            all_files.append((full, rel))

    total = len(all_files)
    print(f"  {total} files extracted", flush=True)

    total_in = 0
    total_out = 0
    resized_count = 0

    with zipfile.ZipFile(DST, 'w', zipfile.ZIP_STORED) as zout:
        for i, (full_path, rel_name) in enumerate(all_files, 1):
            data = open(full_path, 'rb').read()
            total_in += len(data)
            ext_f = rel_name.rsplit('.', 1)[-1].lower() if '.' in rel_name else ''

            if ext_f in IMAGE_EXTS:
                try:
                    img = Image.open(io.BytesIO(data))
                    w, h = img.size
                    longest = max(w, h)
                    if MAX_SIZE > 0 and longest > MAX_SIZE:
                        scale = MAX_SIZE / longest
                        new_w = int(w * scale)
                        new_h = int(h * scale)
                        img = img.resize((new_w, new_h), Image.LANCZOS)
                        resized_count += 1
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGBA')
                    else:
                        img = img.convert('RGB')
                    buf = io.BytesIO()
                    img.save(buf, format='AVIF', quality=QUALITY, speed=6)
                    out_data = buf.getvalue()
                    new_name = rel_name.rsplit('.', 1)[0] + '.avif'
                    zout.writestr(new_name, out_data)
                    total_out += len(out_data)
                    ratio = len(out_data) / len(data) * 100
                    if i % 20 == 0 or i == total:
                        elapsed = time.time() - start
                        eta = elapsed / i * (total - i)
                        print(f"[{i}/{total}] {ratio:.0f}% | Elapsed: {elapsed:.0f}s | ETA: {eta:.0f}s", flush=True)
                except Exception as e:
                    print(f"  ERROR converting {rel_name}: {e}, keeping original", flush=True)
                    zout.writestr(rel_name, data)
                    total_out += len(data)
            else:
                zout.writestr(rel_name, data)
                total_out += len(data)

in_size = os.path.getsize(SRC)
out_size = os.path.getsize(DST)
elapsed = time.time() - start
print(f"\nDone in {elapsed:.0f}s")
print(f"Input:  {in_size/1024/1024:.1f} MB")
print(f"Output: {out_size/1024/1024:.1f} MB")
print(f"Ratio: {out_size/in_size*100:.1f}%")
print(f"Resized: {resized_count} images (max {MAX_SIZE}px)")
