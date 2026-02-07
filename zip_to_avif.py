import zipfile
import os
import sys
import io
import time
from pathlib import Path

import pillow_avif
from PIL import Image

SRC = sys.argv[1]
DST = sys.argv[2]
QUALITY = int(sys.argv[3])
MAX_SIZE = int(sys.argv[4]) if len(sys.argv) > 4 else 3000

start = time.time()

with zipfile.ZipFile(SRC, 'r') as zin, zipfile.ZipFile(DST, 'w', zipfile.ZIP_STORED) as zout:
    entries = zin.namelist()
    total = len(entries)
    total_in = 0
    total_out = 0
    resized_count = 0

    for i, name in enumerate(entries, 1):
        data = zin.read(name)
        total_in += len(data)
        ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''

        if ext in ('jpg', 'jpeg', 'png', 'webp', 'bmp'):
            try:
                img = Image.open(io.BytesIO(data))
                # リサイズ: 長辺がMAX_SIZEを超えていたら縮小
                w, h = img.size
                longest = max(w, h)
                if longest > MAX_SIZE:
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
                new_name = name.rsplit('.', 1)[0] + '.avif'
                zout.writestr(new_name, out_data)
                total_out += len(out_data)
                ratio = len(out_data) / len(data) * 100
                if i % 20 == 0 or i == total:
                    elapsed = time.time() - start
                    eta = elapsed / i * (total - i)
                    print(f"[{i}/{total}] {ratio:.0f}% | Elapsed: {elapsed:.0f}s | ETA: {eta:.0f}s", flush=True)
            except Exception as e:
                print(f"  ERROR converting {name}: {e}, keeping original", flush=True)
                zout.writestr(name, data)
                total_out += len(data)
        else:
            zout.writestr(name, data)
            total_out += len(data)

elapsed = time.time() - start
print(f"\nDone in {elapsed:.0f}s")
print(f"Input total:  {total_in/1024/1024:.1f} MB")
print(f"Output total: {total_out/1024/1024:.1f} MB")
print(f"Ratio: {total_out/total_in*100:.1f}%")
print(f"Resized: {resized_count} images (max {MAX_SIZE}px)")
