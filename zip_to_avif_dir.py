#!/usr/bin/env python3
"""ディレクトリ内のアーカイブ・画像フォルダを一括でAVIF変換するツール。
中身を分析し、変換対象を選択できる。
"""

import os
import sys
import re
import zipfile
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

ARCHIVE_EXTS = {'zip', 'rar', '7z', 'cbz', 'cbr'}
IMAGE_EXTS = {'jpg', 'jpeg', 'png', 'webp', 'avif', 'bmp', 'gif'}
HEAVY_EXTS = {'jpg', 'jpeg', 'png', 'bmp'}
LIGHT_EXTS = {'avif', 'webp'}


def to_wsl_path(p):
    m = re.match(r'^([A-Za-z]):[/\\]', p)
    if m:
        drive = m.group(1).lower()
        rest = p[3:].replace('\\', '/')
        return f'/mnt/{drive}/{rest}'
    return p


# --- アーカイブ分析 ---

def list_archive_images(path):
    """アーカイブ内の画像ファイル拡張子リストを返す（展開せず）"""
    ext = path.rsplit('.', 1)[-1].lower()
    entries = []

    try:
        if ext in ('zip', 'cbz'):
            with zipfile.ZipFile(path, 'r') as z:
                entries = [n for n in z.namelist() if not n.endswith('/')]
        elif ext in ('rar', 'cbr'):
            result = subprocess.run(
                ['unar', '-l', path],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                in_list = False
                for line in result.stdout.splitlines():
                    stripped = line.strip()
                    if stripped.startswith('..'):
                        in_list = True
                        continue
                    if in_list and stripped and not stripped.startswith('('):
                        if '/' != stripped[-1:]:
                            entries.append(stripped)
        elif ext == '7z':
            result = subprocess.run(
                ['7z', 'l', '-slt', path],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith('Path = ') and line.count('.') > 0:
                        entries.append(line[7:])
    except Exception:
        pass

    image_exts = []
    for entry in entries:
        if '.' in entry:
            e = entry.rsplit('.', 1)[-1].lower()
            if e in IMAGE_EXTS:
                image_exts.append(e)
    return image_exts


def analyze_archive(path):
    """アーカイブを分析して情報を返す"""
    basename = os.path.basename(path)
    size = os.path.getsize(path)
    exts = list_archive_images(path)

    return _build_info(path, basename, size, exts, entry_type='archive')


# --- 画像フォルダ分析 ---

def list_folder_images(dir_path):
    """フォルダ内の画像ファイル拡張子リストを返す（再帰）"""
    exts = []
    for root, dirs, files in os.walk(dir_path):
        for f in files:
            if '.' in f:
                e = f.rsplit('.', 1)[-1].lower()
                if e in IMAGE_EXTS:
                    exts.append(e)
    return exts


def get_folder_size(dir_path):
    """フォルダの合計サイズ（全ファイル）"""
    total = 0
    for root, dirs, files in os.walk(dir_path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def analyze_folder(dir_path, base_dir):
    """画像フォルダを分析して情報を返す"""
    rel = os.path.relpath(dir_path, base_dir)
    basename = rel + '/'
    size = get_folder_size(dir_path)
    exts = list_folder_images(dir_path)

    return _build_info(dir_path, basename, size, exts, entry_type='folder')


# --- 共通 ---

def _build_info(path, basename, size, exts, entry_type):
    total = len(exts)
    heavy = sum(1 for e in exts if e in HEAVY_EXTS)
    light = sum(1 for e in exts if e in LIGHT_EXTS)

    if total > 0:
        light_pct = light / total * 100
        c = Counter(exts)
        dominant = c.most_common(1)[0]
        fmt_str = f"{dominant[0].upper()} {dominant[1] / total * 100:.0f}%"
    else:
        light_pct = 0
        fmt_str = "no images"

    name_part = os.path.basename(path.rstrip('/'))
    if '_avif' in name_part.rsplit('.', 1)[0]:
        status = 'already converted'
    elif total > 0 and light_pct >= 80:
        status = 'already light'
    else:
        status = 'compress'

    return {
        'path': path,
        'basename': basename,
        'size': size,
        'fmt': fmt_str,
        'status': status,
        'type': entry_type,
        'image_count': total,
        'heavy_count': heavy,
        'light_pct': light_pct,
    }


def format_size(size):
    if size >= 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024 / 1024:.1f}GB"
    elif size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.0f}MB"
    else:
        return f"{size / 1024:.0f}KB"


def truncate_name(name, max_len):
    """長いファイル名を省略表示"""
    if len(name) <= max_len:
        return name
    # 拡張子（またはフォルダの/）を保持
    if name.endswith('/'):
        base = name[:-1]
        suffix = '/'
    elif '.' in name:
        base, ext = name.rsplit('.', 1)
        suffix = '.' + ext
    else:
        base = name
        suffix = ''
    keep = max_len - len(suffix) - 2  # 2 for ".."
    if keep < 4:
        return name[:max_len - 2] + '..'
    return base[:keep] + '..' + suffix


# --- フォルダ変換 ---

def get_image_size(path):
    cmd = [
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height', '-of', 'csv=p=0', path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(',')
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return None, None


def convert_single_image(args):
    """ffmpeg av1_nvencで1枚の画像をAVIFに変換"""
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

    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', in_path]
    if vf_filters:
        cmd += ['-vf', ','.join(vf_filters)]
    cmd += ['-c:v', 'av1_nvenc', '-cq', str(cq),
            '-pix_fmt', 'yuv420p', '-frames:v', '1', out_path]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return False, result.stderr
    return True, None


def convert_folder(dir_path, quality, workers, max_size):
    """フォルダ内の重い画像をAVIFに変換（元ファイルは変換成功後に削除）"""
    quality_i = int(quality)
    workers_i = int(workers)
    max_size_i = int(max_size)

    # 変換対象を収集
    tasks = []
    for root, dirs, files in os.walk(dir_path):
        for f in files:
            if '.' not in f:
                continue
            ext = f.rsplit('.', 1)[-1].lower()
            if ext in HEAVY_EXTS:
                full = os.path.join(root, f)
                out = os.path.join(root, f.rsplit('.', 1)[0] + '.avif')
                tasks.append((full, out))

    if not tasks:
        print("  No heavy images to convert.")
        return

    print(f"  Converting {len(tasks)} images (workers={workers_i}, max_size={max_size_i})...")

    done = 0
    errors = 0
    kept_original = 0
    total_in_size = 0
    total_out_size = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=workers_i) as executor:
        futures = {}
        for in_path, out_path in tasks:
            f = executor.submit(convert_single_image,
                                (in_path, out_path, quality_i, max_size_i))
            futures[f] = (in_path, out_path)

        for future in as_completed(futures):
            in_path, out_path = futures[future]
            done += 1
            success, err = future.result()

            in_size = os.path.getsize(in_path)
            total_in_size += in_size

            if success and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                out_size = os.path.getsize(out_path)
                if out_size < in_size:
                    # 小さくなった → 元ファイルを削除
                    os.remove(in_path)
                    total_out_size += out_size
                else:
                    # 逆に大きくなった → avifを捨てて元を残す
                    os.remove(out_path)
                    total_out_size += in_size
                    kept_original += 1
            else:
                errors += 1
                total_out_size += in_size
                if os.path.exists(out_path):
                    os.remove(out_path)
                if err:
                    print(f"    ERROR {os.path.basename(in_path)}: {err.strip()}")

            if done % 20 == 0 or done == len(tasks):
                elapsed = time.time() - start
                eta = elapsed / done * (len(tasks) - done) if done > 0 else 0
                ratio = total_out_size / total_in_size * 100 if total_in_size > 0 else 0
                print(f"    [{done}/{len(tasks)}] {ratio:.0f}% | Elapsed: {elapsed:.0f}s | ETA: {eta:.0f}s")

    ratio = total_out_size / total_in_size * 100 if total_in_size > 0 else 0
    saved = total_in_size - total_out_size
    print(f"  Result: {format_size(total_in_size)} -> {format_size(total_out_size)} ({ratio:.0f}%, -{format_size(saved)})")
    if kept_original:
        print(f"  {kept_original} files kept original (avif was larger)")
    if errors:
        print(f"  {errors} files failed (originals kept)")


# --- メイン ---

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 zip_to_avif_dir.py <directory> [quality] [workers] [max_size]")
        sys.exit(1)

    dir_path = to_wsl_path(sys.argv[1])
    quality = sys.argv[2] if len(sys.argv) > 2 else '70'
    workers = sys.argv[3] if len(sys.argv) > 3 else '4'
    max_size = sys.argv[4] if len(sys.argv) > 4 else '2000'

    if not os.path.isdir(dir_path):
        print(f"Error: not a directory: {dir_path}")
        sys.exit(1)

    # --- 探索・分析 ---
    infos = scan_directory(dir_path)

    if not infos:
        print(f"No archives or image folders found in {dir_path}")
        sys.exit(0)

    # --- 表示→選択→変換のループ ---
    script = os.path.expanduser('~/bin/zip_to_avif_gpu.py')

    while True:
        show_list(infos)
        try:
            sel = input("Select (e.g. 1,2 / all / r=rescan / q): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            break

        if sel.lower() == 'q' or sel == '':
            print("Done.")
            break

        if sel.lower() == 'r':
            infos = scan_directory(dir_path)
            if not infos:
                print("No archives or image folders found.")
                break
            continue

        selected = parse_selection(sel, len(infos))
        if selected is None:
            continue

        # 変換実行
        total = len(selected)
        for i, idx in enumerate(selected, 1):
            info = infos[idx]

            if info['type'] == 'folder':
                if info['heavy_count'] == 0:
                    print(f"\n[{i}/{total}] Skipping {info['basename']} (no heavy images)")
                    continue
                print(f"\n[{i}/{total}] Converting folder: {info['basename']} "
                      f"({format_size(info['size'])}, {info['heavy_count']} heavy images)")
                convert_folder(info['path'], quality, workers, max_size)
            else:
                src = info['path']
                name_base = os.path.basename(src).rsplit('.', 1)[0]
                out_path = os.path.join(os.path.dirname(src), f"{name_base}_avif.zip")

                if os.path.exists(out_path):
                    ans = input(f"  WARNING: {os.path.basename(out_path)} exists. Overwrite? (y/N): ").strip()
                    if ans.lower() != 'y':
                        print("  Skipped.")
                        continue

                print(f"\n[{i}/{total}] Converting archive: {info['basename']} ({format_size(info['size'])})")
                print(f"  -> {os.path.basename(out_path)}")

                result = subprocess.run(
                    ['python3', script, src, out_path, quality, workers, max_size],
                    stdin=subprocess.DEVNULL, timeout=3600
                )
                if result.returncode != 0:
                    print(f"  ERROR: conversion failed for {info['basename']}")

        print(f"\nBatch done. {total} items processed.")

        # 再スキャンして一覧を更新
        infos = scan_directory(dir_path)
        if not infos:
            print("No more items found.")
            break
        print()


def scan_directory(dir_path):
    """ディレクトリをスキャンしてアーカイブ・画像フォルダの情報リストを返す"""
    print(f"\nScanning {dir_path} ...")

    infos = []

    # アーカイブを再帰探索
    for root, dirs, files in os.walk(dir_path):
        for f in files:
            ext = f.rsplit('.', 1)[-1].lower() if '.' in f else ''
            if ext in ARCHIVE_EXTS:
                infos.append(analyze_archive(os.path.join(root, f)))

    # 画像フォルダ探索（直下のサブディレクトリ単位）
    for entry in os.listdir(dir_path):
        full = os.path.join(dir_path, entry)
        if os.path.isdir(full) and list_folder_images(full):
            infos.append(analyze_folder(full, dir_path))

    # 直下のバラ画像
    info = _build_info_loose(dir_path)
    if info:
        infos.append(info)

    # avif/webpが50%以上のものは除外
    infos = [i for i in infos if i['light_pct'] < 50]

    # サイズ昇順ソート（一番下が一番重い）
    infos.sort(key=lambda x: x['size'])

    return infos


def show_list(infos):
    """一覧を表示"""
    NAME_MAX = 40
    print()
    for idx, info in enumerate(infos, 1):
        marker = '->' if info['status'] == 'compress' else '  '
        tag = info['status']
        name = truncate_name(info['basename'], NAME_MAX)
        extra = f" ({info['image_count']}img)" if info['type'] == 'folder' else ''
        print(f"  [{idx:>3}] {name:<{NAME_MAX}}  {format_size(info['size']):>7}  {info['fmt']:<12} {marker} {tag}{extra}")
    print()


def parse_selection(sel, count):
    """選択文字列をパースしてインデックスリストを返す。エラー時はNone"""
    if sel.lower() == 'all':
        return list(range(count))

    selected = []
    try:
        for part in sel.split(','):
            part = part.strip()
            if not part:
                continue
            if '-' in part:
                a, b = part.split('-', 1)
                selected.extend(range(int(a) - 1, int(b)))
            else:
                selected.append(int(part) - 1)
    except ValueError:
        print(f"Error: invalid input '{sel}'")
        return None

    valid = []
    seen = set()
    for idx in selected:
        if idx < 0 or idx >= count:
            print(f"Error: number {idx + 1} is out of range (1-{count})")
            return None
        if idx not in seen:
            valid.append(idx)
            seen.add(idx)

    if not valid:
        print("Nothing selected.")
        return None

    return valid


def _build_info_loose(dir_path):
    """直下のバラ画像のみ分析（サブディレクトリは含めない）"""
    exts = []
    total_size = 0
    for f in os.listdir(dir_path):
        full = os.path.join(dir_path, f)
        if not os.path.isfile(full):
            continue
        if '.' in f:
            e = f.rsplit('.', 1)[-1].lower()
            if e in IMAGE_EXTS:
                exts.append(e)
                total_size += os.path.getsize(full)

    if not exts:
        return None

    return _build_info(dir_path, './', total_size, exts, entry_type='folder')


if __name__ == '__main__':
    main()
