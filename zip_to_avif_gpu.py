#!/usr/bin/env python3
"""アーカイブ内の画像をAVIFに変換（NVIDIA GPU使用版）
対応形式: zip, rar, 7z
RTX 40系のAV1ハードウェアエンコーダ(NVENC)を使用して高速変換。
"""

import zipfile
import os
import sys
import subprocess
import tempfile
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

IMAGE_EXTS = {'jpg', 'jpeg', 'png', 'webp', 'bmp'}
ARCHIVE_EXTS = {'zip', 'rar', '7z', 'cbz', 'cbr'}


def to_wsl_path(p):
    """Windowsパスを自動的にWSLパスに変換"""
    import re
    m = re.match(r'^([A-Za-z]):[/\\]', p)
    if m:
        drive = m.group(1).lower()
        rest = p[3:].replace('\\', '/')
        return f'/mnt/{drive}/{rest}'
    return p


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


def get_image_size(path):
    """ffprobeで画像サイズを取得"""
    cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'csv=p=0',
        path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode == 0 and result.stdout.strip():
        parts = result.stdout.strip().split(',')
        return int(parts[0]), int(parts[1])
    return None, None


def convert_image(args):
    """ffmpeg av1_nvencで画像をAVIFに変換（リサイズ対応）"""
    in_path, out_path, quality, max_size = args
    cq = max(1, min(51, int(51 - quality * 0.51)))

    vf_filters = []
    if max_size > 0:
        w, h = get_image_size(in_path)
        if w and h and max(w, h) > max_size:
            if w >= h:
                vf_filters.append(f'scale={max_size}:-2')
            else:
                vf_filters.append(f'scale=-2:{max_size}')

    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        '-i', in_path,
    ]
    if vf_filters:
        cmd += ['-vf', ','.join(vf_filters)]
    cmd += [
        '-c:v', 'av1_nvenc',
        '-cq', str(cq),
        '-pix_fmt', 'yuv420p',
        '-frames:v', '1',
        out_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return None, result.stderr
    return out_path, None


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 zip_to_avif_gpu.py <入力アーカイブ> <出力ZIP> <品質(1-100)> [並列数] [最大辺px]")
        print("  対応形式: zip, rar, 7z, cbz, cbr")
        print("  品質の目安: 60=最大圧縮, 75=推奨, 85=高画質")
        print("  最大辺: 長辺がこのpxを超える画像を縮小（デフォルト3000、0で無効）")
        sys.exit(1)

    src = to_wsl_path(sys.argv[1])
    dst = to_wsl_path(sys.argv[2])
    quality = int(sys.argv[3])
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    max_size = int(sys.argv[5]) if len(sys.argv) > 5 else 3000

    # 入力ファイルチェック
    if not os.path.isfile(src):
        print(f"エラー: ファイルが見つかりません: {src}")
        sys.exit(1)

    ext = src.rsplit('.', 1)[-1].lower() if '.' in src else ''
    if ext not in ARCHIVE_EXTS:
        print(f"エラー: 未対応の形式です (.{ext})")
        print(f"  対応形式: {', '.join(sorted(ARCHIVE_EXTS))}")
        sys.exit(1)

    start = time.time()

    with tempfile.TemporaryDirectory() as tmpdir:
        in_dir = os.path.join(tmpdir, 'in')
        out_dir = os.path.join(tmpdir, 'out')
        os.makedirs(in_dir)
        os.makedirs(out_dir)

        # アーカイブを展開
        print("Extracting archive...", flush=True)
        extract_archive(src, in_dir)

        # 展開されたファイルを走査
        all_files = []
        for root, dirs, files in os.walk(in_dir):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, in_dir)
                all_files.append((full, rel))

        print(f"  {len(all_files)} files extracted", flush=True)

        # 変換タスクを準備
        tasks = []
        non_image_files = []
        for full_path, rel_name in all_files:
            ext_f = rel_name.rsplit('.', 1)[-1].lower() if '.' in rel_name else ''
            if ext_f in IMAGE_EXTS:
                out_name = rel_name.rsplit('.', 1)[0] + '.avif'
                out_path = os.path.join(out_dir, out_name)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                tasks.append((full_path, out_path, quality, rel_name, out_name))
            else:
                non_image_files.append((full_path, rel_name))

        # GPU並列変換
        print(f"Converting {len(tasks)} images with GPU (workers={workers}, max_size={max_size})...", flush=True)
        results = {}
        errors = 0
        done = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for in_path, out_path, q, orig_name, new_name in tasks:
                f = executor.submit(convert_image, (in_path, out_path, q, max_size))
                futures[f] = (orig_name, new_name, in_path, out_path)

            for future in as_completed(futures):
                orig_name, new_name, in_path, out_path = futures[future]
                done += 1
                result_path, err = future.result()

                if result_path and os.path.exists(result_path):
                    results[new_name] = result_path
                else:
                    results[orig_name] = in_path
                    errors += 1
                    if err:
                        print(f"  ERROR {orig_name}: {err.strip()}", flush=True)

                if done % 20 == 0 or done == len(tasks):
                    elapsed = time.time() - start
                    eta = elapsed / done * (len(tasks) - done) if done > 0 else 0
                    print(f"  [{done}/{len(tasks)}] Elapsed: {elapsed:.0f}s | ETA: {eta:.0f}s", flush=True)

        # 新しいZIPを作成
        print("Creating output ZIP...", flush=True)
        total_out = 0

        with zipfile.ZipFile(dst, 'w', zipfile.ZIP_STORED) as zout:
            for name, path in sorted(results.items()):
                data = open(path, 'rb').read()
                zout.writestr(name, data)
                total_out += len(data)

            for full_path, rel_name in non_image_files:
                data = open(full_path, 'rb').read()
                zout.writestr(rel_name, data)
                total_out += len(data)

        in_size = os.path.getsize(src)
        out_size = os.path.getsize(dst)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s")
    print(f"Input:  {in_size/1024/1024:.1f} MB")
    print(f"Output: {out_size/1024/1024:.1f} MB")
    print(f"Ratio: {out_size/in_size*100:.1f}%")
    if errors:
        print(f"Errors: {errors} files kept original")


if __name__ == '__main__':
    main()
