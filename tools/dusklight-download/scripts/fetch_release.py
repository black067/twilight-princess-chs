#!/usr/bin/env python3
"""按 config.json 拉取各来源 Release 的资产。

下载什么由配置文件决定，命令行参数覆盖配置；本脚本只含核心逻辑。
只依赖标准库，Windows / macOS / Linux 通用。用法见 ../README.md。
"""

import argparse
import fnmatch
import json
import os
import sys
import time
import urllib.error
import urllib.request

import common

API = "https://api.github.com"
UA = "dusklight-download"
CHUNK = 1 << 16
TRIES = 3
RETRY_DELAY = 5
PROGRESS = sys.stdout.isatty()


def human(size):
    return "%.1f MB" % (size / 1048576)


def api_headers():
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def get_release(repo, tag, headers):
    if tag.lower() == "latest":
        url = "%s/repos/%s/releases/latest" % (API, repo)
    else:
        url = "%s/repos/%s/releases/tags/%s" % (API, repo, tag)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def pick_assets(assets, filters):
    if not filters:
        return list(assets)
    picked = []
    for asset in assets:
        name = asset["name"].lower()
        if any(fnmatch.fnmatchcase(name, f.lower()) for f in filters):
            picked.append(asset)
    return picked


def download(url, target, size):
    """下载到 target，尽量按 Range 断点续传，返回最终字节数。"""
    pos = target.stat().st_size if target.exists() else 0
    if pos > size:
        pos = 0
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if pos:
        req.add_header("Range", "bytes=%d-" % pos)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and pos == size:
            return pos
        raise
    with resp:
        if pos and resp.status != 206:
            pos = 0
        with open(target, "ab" if pos else "wb") as fh:
            done, shown = pos, -1
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if PROGRESS and size:
                    pct = done * 100 // size
                    if pct != shown:
                        shown = pct
                        sys.stdout.write("\r    %s / %s" % (human(done), human(size)))
                        sys.stdout.flush()
            if PROGRESS and shown >= 0:
                sys.stdout.write("\r")
    return target.stat().st_size


def fetch_asset(asset, target):
    for attempt in range(1, TRIES + 1):
        try:
            got = download(asset["browser_download_url"], target, asset["size"])
            if got == asset["size"]:
                return True
            print("    字节数不符：%d != %d" % (got, asset["size"]))
        except OSError as exc:
            print("    下载出错：%s" % exc)
        if attempt < TRIES:
            time.sleep(RETRY_DELAY)
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="按 config.json 拉取各来源 Release 的资产")
    parser.add_argument("--config", metavar="PATH", help="配置文件，默认 config.json")
    parser.add_argument("--repo", metavar="OWNER/NAME", help="只处理该来源（配置里有同源时沿用其过滤）")
    parser.add_argument("--tag", metavar="TAG", help="版本 tag，或 latest 取最新正式 Release")
    parser.add_argument("--assets", metavar="GLOB", action="append",
                        help="本次全部来源的资产名通配符，可多次传")
    parser.add_argument("--dist", metavar="DIR", help="输出根目录，覆盖配置")
    parser.add_argument("--plan", action="store_true", help="只打印计划，不下载")
    args = parser.parse_args(argv)

    cfg_path = common.config_path(args.config)
    if not cfg_path.exists():
        print("缺少配置文件：%s" % cfg_path)
        return 1
    try:
        cfg = common.load_config(args.config)
    except json.JSONDecodeError as exc:
        print("配置文件不是合法 JSON：%s\n%s" % (cfg_path, exc))
        return 1
    print("Config: %s" % cfg_path)

    sources = [s for s in (cfg.get("sources") or []) if isinstance(s, dict) and s.get("repo")]
    if not sources:
        print("%s 里没有配置任何来源" % cfg_path)
        return 1

    if args.repo:
        matched = [s for s in sources if s["repo"].lower() == args.repo.lower()]
        sources = matched or [{"repo": args.repo}]
    if args.tag and len(sources) > 1:
        print("配置有 %d 个来源，--tag 需配合 --repo 指定唯一来源" % len(sources))
        return 1

    dist_root = common.dist_root(cfg, args.dist)
    headers = api_headers()
    failed = []

    for source in sources:
        repo = source["repo"]
        if "/" not in repo:
            print("来源需为 owner/name 格式：%s" % repo)
            failed.append(repo)
            continue
        tag = args.tag or source.get("tag") or "latest"
        try:
            release = get_release(repo, tag, headers)
        except urllib.error.HTTPError as exc:
            hint = "，可设 GITHUB_TOKEN 提高限额" if exc.code == 403 else ""
            print("== %s @ %s：HTTP %s %s%s" % (repo, tag, exc.code, exc.reason, hint))
            failed.append("%s@%s" % (repo, tag))
            continue
        except OSError as exc:
            print("== %s @ %s：%s" % (repo, tag, exc))
            failed.append("%s@%s" % (repo, tag))
            continue
        tag = release["tag_name"]

        filters = args.assets if args.assets else source.get("assets")
        if isinstance(filters, str):
            filters = [filters]
        filters = [f for f in (filters or []) if f]
        assets = pick_assets(release.get("assets") or [], filters)
        if not assets:
            print("== %s @ %s：过滤后没有可下载的资产" % (repo, tag))
            failed.append("%s@%s" % (repo, tag))
            continue

        target_dir = dist_root.joinpath(*repo.split("/"), tag)
        print("== %s @ %s -> %s（%d 个资产）" % (repo, tag, target_dir, len(assets)))
        if args.plan:
            for asset in assets:
                print("   %s (%s)" % (asset["name"], human(asset["size"])))
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        for asset in assets:
            target = target_dir / asset["name"]
            if target.exists() and target.stat().st_size == asset["size"]:
                print("==> %s 已存在，跳过" % asset["name"])
                continue
            print("==> %s (%s)" % (asset["name"], human(asset["size"])))
            if fetch_asset(asset, target):
                print("    完成 %s" % human(asset["size"]))
            else:
                failed.append("%s@%s %s" % (repo, tag, asset["name"]))

    if failed:
        print("失败 %d 项：" % len(failed))
        for item in failed:
            print("  %s" % item)
        return 1
    if args.plan:
        print("仅计划，未下载。")
        return 0
    print("全部资产已下载到 %s" % dist_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
