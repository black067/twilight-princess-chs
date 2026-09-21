#!/usr/bin/env python3
"""用 7-Zip 把单文件切成等长 zip 分卷。

7z 按平台在 PATH 与常见安装位置里找；只依赖标准库。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

NAMES = ("7z", "7z.exe", "7za", "7zz")
FALLBACKS = {
    "nt": ("C:/Program Files/7-Zip/7z.exe", "C:/Program Files (x86)/7-Zip/7z.exe"),
    "darwin": ("/opt/homebrew/bin/7z", "/usr/local/bin/7z"),
}
FALLBACKS_DEFAULT = ("/usr/bin/7z", "/usr/bin/7za", "/usr/bin/7zz")


def find_7z():
    for name in NAMES:
        found = shutil.which(name)
        if found:
            return found
    for path in FALLBACKS.get(os.name, ()) + FALLBACKS_DEFAULT:
        if Path(path).exists():
            return path
    return None


def human(size):
    return "%.1f MB" % (size / 1048576)


def main(argv=None):
    parser = argparse.ArgumentParser(description="用 7-Zip 把单文件切成等长 zip 分卷")
    parser.add_argument("source", help="要切的文件")
    parser.add_argument("dest_dir", help="分卷输出的目录")
    parser.add_argument("--volume-size", default="600m", metavar="SIZE",
                        help="每卷大小（7z 语法，如 600m），默认 600m")
    args = parser.parse_args(argv)

    seven = find_7z()
    if seven is None:
        print("找不到 7z：Windows 装 7-Zip，Linux 装 p7zip，macOS 用 brew 装 p7zip")
        return 1

    source = Path(args.source)
    if not source.exists():
        print("缺少要切的文件：%s" % source)
        return 1

    dest = Path(args.dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    base = dest / ("%s-split%s" % (source.stem, source.suffix))

    cmd = [seven, "a", "-tzip", "-mx0", "-v" + args.volume_size, "-y",
           str(base), str(source.resolve())]
    code = subprocess.call(cmd)
    if code != 0:
        print("7z 退出码 %d" % code)
        return 1

    for part in sorted(dest.glob("%s-split%s.*" % (source.stem, source.suffix))):
        print("%-64s %s" % (part.name, human(part.stat().st_size)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
