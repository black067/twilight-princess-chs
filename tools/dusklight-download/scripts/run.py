#!/usr/bin/env python3
"""用 game/ 里的 dusklight 启动光盘镜像。

dist 目录取自 config.json（缺失则用默认 dist/）；可执行文件按平台取名
（Windows 是 dusklight.exe，其余是 dusklight）。只依赖标准库。
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import common

EXE_NAMES = ("dusklight.exe", "dusklight")
# 当前平台可用的包名备选（按先后优先），两仓库命名不同所以列了两种
PORTABLE = {
    "nt": ("*-win32-*-portable.zip", "*-win32-*-x86_64.zip"),
    "darwin": ("*-macos-*-portable.tar.gz", "*-macos-*-x86_64.zip"),
}
PORTABLE_DEFAULT = ("*-linux-*-portable.tar.gz", "*-linux-*-x86_64.AppImage")


def find_exe(game):
    for name in EXE_NAMES:
        exe = game / name
        if exe.exists():
            return exe
    return None


def portable_hint(dist):
    """找最近下载的、当前平台可用的包，用于提示解压哪个。"""
    for pattern in PORTABLE.get(os.name, PORTABLE_DEFAULT):
        hits = [p for p in dist.rglob(pattern) if p.is_file()]
        if hits:
            return max(hits, key=lambda p: p.stat().st_mtime)
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="用 game/ 里的 dusklight 启动光盘镜像")
    parser.add_argument("--disc", metavar="PATH", help="光盘镜像，默认 <dist>/RZDP01.wbfs")
    args = parser.parse_args(argv)

    cfg = common.load_config()
    dist = common.dist_root(cfg)
    game = common.ROOT / "game"

    exe = find_exe(game)
    if exe is None:
        print("缺少 %s" % (game / EXE_NAMES[0]))
        hint = portable_hint(dist)
        if hint:
            print("先解压 %s 到 game/" % hint)
        else:
            print("先下载并解压对应平台的便携包到 game/：python scripts/fetch_release.py")
        return 1

    disc = Path(args.disc) if args.disc else dist / "RZDP01.wbfs"
    if not disc.exists():
        print("缺少 %s" % disc)
        return 1

    subprocess.Popen([str(exe), "--dvd", str(disc.resolve())], cwd=str(game))
    return 0


if __name__ == "__main__":
    sys.exit(main())
