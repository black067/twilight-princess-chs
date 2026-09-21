import json
import os
import sys
import zipfile

import paths

PARTS = os.path.join(paths.WORK, "sjis_parts")

# 历代旧 mod 的开关，安装时统一关掉（同批文件只能有一个生效）
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

# name/description 里 {region} / {language} 的展开（写给玩家看的中文）
SLOT_NAMES = {
    "region": {"us": "美", "eu": "欧", "jp": "日"},
    "language": {"us": "英语", "uk": "英式英语", "de": "德语", "fr": "法语",
                 "sp": "西班牙语", "it": "意大利语", "jp": "日语"},
}


def fill_slot(text, region, language):
    return (text.replace("{region}", SLOT_NAMES["region"][region])
                .replace("{language}", SLOT_NAMES["language"][language]))


def main():
    mod = paths.config_value("mod")
    if not isinstance(mod, dict) or not mod.get("id"):
        sys.exit("%s 里缺 mod 元信息（id/name/version/author/description）" % paths.CONFIG)
    region, language = paths.slot()
    mod = dict(mod)
    mod["name"] = fill_slot(str(mod.get("name", "")), region, language)
    mod["description"] = fill_slot(str(mod.get("description", "")), region, language)
    stem = paths.escape_mod_id(mod["id"])
    out = paths.mod_path()
    enable = "mod.%s.enabled" % stem

    os.makedirs(os.path.dirname(out), exist_ok=True)
    files = []
    dirs = set()
    for entry in sorted(os.listdir(PARTS)):
        parts = entry.split("_", 2)
        if len(parts) != 3 or parts[0] != "res":
            continue
        dirs.add(parts[1])
        files.append(("overlay/res/%s/%s" % (parts[1], parts[2]), os.path.join(PARTS, entry)))
    assert files, "no parts found"
    other = sorted(dirs - {paths.font_dir(), paths.msg_dir()})
    if other:
        print("提示：部件里还有非当前槽位的目录：%s" % ", ".join(other))

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mod.json", json.dumps(mod, indent=2) + "\n")
        for arcname, path in sorted(files):
            z.write(path, arcname)
    print("built %s  %d bytes  %d overlays（槽位 %s/%s：res/%s + res/%s）"
          % (out, os.path.getsize(out), len(files), region, language,
             paths.msg_dir(), paths.font_dir()))
    for arcname, _ in sorted(files):
        print("   %s" % arcname)

    game_dir = paths.option("--game-dir")
    if not game_dir:
        print("未配置 game_dir，跳过安装")
        return
    game_mods = os.path.join(game_dir, "data", "mods")
    os.makedirs(game_mods, exist_ok=True)
    dst = os.path.join(game_mods, stem + ".dusk")
    with open(out, "rb") as a, open(dst, "wb") as b:
        b.write(a.read())
    print("installed -> %s" % dst)

    config = os.path.join(game_dir, "data", "config.json")
    with open(config, encoding="utf-8") as f:
        cfg = json.load(f)
    for key in DISABLE:
        cfg[key] = False
    cfg[enable] = True
    cfg["game.enableChineseNameKeyboard"] = True
    with open(config, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)
    print("config: %s = True, game.enableChineseNameKeyboard = True, others off" % enable)


main()
