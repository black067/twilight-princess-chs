"""把 dist 里的成品包装进游戏目录。

  python scripts/install.py --region us                    # 装美版盘（开源字体包）
  python scripts/install.py --region jp --variant origin   # 装日版盘（保留原字库位图的包）
  python scripts/install.py --list                      # 只看现状

mod 目录与游戏配置用 --mods-dir / --game-config，或 config 的 mods_dir / game_config
（dusklight 2.x 与 dusk-cn 的布局不同，两者各填各的）。
"""
import json
import os
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths

# 历代旧 mod 的开关，安装时统一关掉（同一批资源只能有一个包生效）
DISABLE = (
    "mod.cn_text_sjis.enabled",
    "mod.cn_text_fr.enabled",
    "mod.cn_text_test99.enabled",
    "mod.cn_text_a.enabled",
    "mod.cn_text_b.enabled",
    "mod.cn_text_b2.enabled",
    "mod.cn_text_full.enabled",
    "mod.cn_font_fix.enabled",
)


def jobs():
    """[(变体, 地区, 语言, mod id, 包路径)]：config 的 discs x 两个变体。"""
    out = []
    for variant, _ in paths.VARIANTS:
        for region, language in paths.discs():
            out.append((variant, region, language,
                        paths.mod_meta(variant, region, language)["id"],
                        paths.package_path(variant, region, language)))
    return out


def known_mods(mods_dir):
    """扫 data/mods 下的 .dusk，返回 [(文件名, 工作目录里的 id, author)]（读不出 mod.json 的记 None）。"""
    found = []
    if not os.path.isdir(mods_dir):
        return found
    for name in sorted(os.listdir(mods_dir)):
        if not name.endswith(".dusk"):
            continue
        meta = {}
        try:
            with zipfile.ZipFile(os.path.join(mods_dir, name)) as z:
                meta = json.loads(z.read("mod.json"))
        except (OSError, ValueError, KeyError):
            meta = {}
        found.append((name, meta.get("id"), meta.get("author")))
    return found


def read_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_config(path, cfg):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)
        f.write("\n")


def main():
    all_jobs = jobs()
    mods_dir = paths.mods_dir()
    config_path = paths.game_config()
    cfg = read_config(config_path)

    if "--list" in sys.argv:
        print("mod 目录: %s" % mods_dir)
        ours = {i for *_, i, _ in all_jobs}
        for name, mod_id, author in known_mods(mods_dir):
            key = "mod.%s.enabled" % paths.escape_mod_id(mod_id) if mod_id else None
            state = "?" if key is None else ("启用" if cfg.get(key) else "停用")
            mark = " <== 本 mod" if mod_id in ours else ""
            print("  %-30s id=%-24s %s%s" % (name, mod_id or "(读不到)", state, mark))
        return

    variant = str(paths.cli("--variant") or paths.OPEN_VARIANT).lower()
    if variant not in dict(paths.VARIANTS):
        sys.exit("--variant 只支持 %s" % " / ".join(v for v, _ in paths.VARIANTS))
    region, language = paths.pick_disc(paths.cli("--region"))
    src = paths.package_path(variant, region, language)
    if not os.path.exists(src):
        sys.exit("找不到成品包：%s（先跑 build_sjis_pack.py）" % src)

    dst = os.path.join(mods_dir, os.path.basename(src))
    os.makedirs(mods_dir, exist_ok=True)
    try:
        shutil.copyfile(src, dst)
    except PermissionError:
        sys.exit("写入被拒：%s。游戏正在运行会占住这个文件，请先完全退出游戏。" % dst)
    print("installed -> %s（%s：%s 变体 / %s 盘）" % (dst, paths.lang(), variant, region))

    # 其余地区/变体的包要清掉：它们覆盖同一批资源，同时留着可能被同时加载
    for other_variant, other_region, _l, _i, other_path in all_jobs:
        if (other_variant, other_region) == (variant, region):
            continue
        stale = os.path.join(mods_dir, os.path.basename(other_path))
        if os.path.exists(stale):
            os.remove(stale)
            print("removed  -> %s（其他地区/变体）" % stale)

    enabled_id = next(i for v, r, _l, i, _p in all_jobs if (v, r) == (variant, region))
    enabled = "mod.%s.enabled" % paths.escape_mod_id(enabled_id)
    for key in list(DISABLE) + ["mod.%s.enabled" % paths.escape_mod_id(i)
                                for v, r, _l, i, _p in all_jobs
                                if (v, r) != (variant, region)]:
        cfg[key] = False
    cfg[enabled] = True
    cfg["game.enableChineseNameKeyboard"] = True
    write_config(config_path, cfg)
    print("config: %s = True，其余本 mod 开关已关" % enabled)

    # 改过 id / 改过包名的旧包脚本管不着，这里只提醒（同一作者才可能与本 mod 重叠）
    our_ids = {i for *_, i, _ in all_jobs}
    authors = {str((paths.lang_value(k) or {}).get("author") or "")
               for _, k in paths.VARIANTS}
    for name, mod_id, mod_author in known_mods(mods_dir):
        if not mod_id or mod_id in our_ids:
            continue
        if authors and mod_author not in authors:
            continue
        if cfg.get("mod.%s.enabled" % paths.escape_mod_id(mod_id)):
            print("注意：%s（id=%s）也开着，它和本 mod 覆盖资源重叠，建议删掉" % (name, mod_id))


main()
