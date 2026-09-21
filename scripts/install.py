"""把 dist 里的成品包装进游戏目录。

  python scripts/install.py                  # 装开源字体包（open）
  python scripts/install.py --variant ique   # 装官方字库包
  python scripts/install.py --list           # 只看现状
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


def mod_ids():
    """{变体: mod id}：直接取 config 里 mod / mod_ique 两段。"""
    ids = {}
    for variant, key in paths.VARIANTS:
        meta = paths.config_value(key)
        if not isinstance(meta, dict) or not meta.get("id"):
            sys.exit("%s 里缺 %s.id" % (paths.CONFIG_EXAMPLE, key))
        ids[variant] = str(meta["id"])
    return ids


def package_path(mod_id):
    out = paths.config_dir("out", os.path.join("work", "mods"))
    return os.path.join(out, paths.escape_mod_id(mod_id) + ".dusk")


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
    ids = mod_ids()
    game_dir = paths.game_dir()
    mods_dir = os.path.join(game_dir, "data", "mods")
    config_path = os.path.join(game_dir, "data", "config.json")
    cfg = read_config(config_path)

    if "--list" in sys.argv:
        print("游戏目录: %s" % game_dir)
        ours = set(ids.values())
        for name, mod_id, author in known_mods(mods_dir):
            key = "mod.%s.enabled" % paths.escape_mod_id(mod_id) if mod_id else None
            state = "?" if key is None else ("启用" if cfg.get(key) else "停用")
            mark = " <== 本 mod" if mod_id in ours else ""
            print("  %-26s id=%-18s %s%s" % (name, mod_id or "(读不到)", state, mark))
        return

    variant = str(paths.option("--variant") or "open").lower()
    if variant not in ids:
        sys.exit("--variant 只支持 open 或 ique：%s" % variant)
    src = package_path(ids[variant])
    if not os.path.exists(src):
        sys.exit("找不到成品包：%s（先跑 build_sjis_pack.py）" % src)

    dst = os.path.join(mods_dir, os.path.basename(src))
    os.makedirs(mods_dir, exist_ok=True)
    try:
        shutil.copyfile(src, dst)
    except PermissionError:
        sys.exit("写入被拒：%s。游戏正在运行会占住这个文件，请先完全退出游戏。" % dst)
    print("installed -> %s（%s 变体）" % (dst, variant))

    # 另一个变体的包要清掉：两个包覆盖同一批资源，同时留着可能被同时加载
    for other, other_id in ids.items():
        if other == variant:
            continue
        stale = os.path.join(mods_dir, paths.escape_mod_id(other_id) + ".dusk")
        if os.path.exists(stale):
            os.remove(stale)
            print("removed  -> %s（另一个变体）" % stale)

    enabled = "mod.%s.enabled" % paths.escape_mod_id(ids[variant])
    for key in list(DISABLE) + ["mod.%s.enabled" % paths.escape_mod_id(i)
                                for i in ids.values() if i != ids[variant]]:
        cfg[key] = False
    cfg[enabled] = True
    cfg["game.enableChineseNameKeyboard"] = True
    write_config(config_path, cfg)
    print("config: %s = True，其余本 mod 开关已关" % enabled)

    # 改过 id / 改过包名的旧包脚本管不着，这里只提醒（同一作者才可能与本 mod 重叠）
    our_ids = set(ids.values())
    authors = {str((paths.config_value(k) or {}).get("author") or "")
               for _, k in paths.VARIANTS}
    for name, mod_id, mod_author in known_mods(mods_dir):
        if not mod_id or mod_id in our_ids:
            continue
        if authors and mod_author not in authors:
            continue
        if cfg.get("mod.%s.enabled" % paths.escape_mod_id(mod_id)):
            print("注意：%s（id=%s）也开着，它和本 mod 覆盖资源重叠，建议删掉" % (name, mod_id))


main()
