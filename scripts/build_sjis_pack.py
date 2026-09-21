import json
import os
import sys
import zipfile

import paths

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.join(paths.WORK, "sjis_parts")
OUT = os.path.join(paths.WORK, "mods", "cn_text_sjis.dusk")

MOD = {
    "id": "cn.text.sjis",
    "name": "CN text (Shift-JIS re-encode, French slot)",
    "version": "2.0.0",
    "author": "Yiga Clan",
    "description": "CN messages re-encoded into a zero-byte-free Shift-JIS code space with a matching font map, so the engine's byte-string operations no longer truncate text.",
}

ENABLE = "mod.cn_text_sjis.enabled"
DISABLE = (
    "mod.cn_text_fr.enabled",
    "mod.cn_text_test99.enabled",
    "mod.cn_text_a.enabled",
    "mod.cn_text_b.enabled",
    "mod.cn_text_b2.enabled",
    "mod.cn_text_full.enabled",
    "mod.cn_font_fix.enabled",
)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    files = []
    for name in sorted(os.listdir(PARTS)):
        parts = name.split("_", 2)
        if len(parts) != 3 or parts[0] != "res":
            continue
        files.append(("overlay/res/%s/%s" % (parts[1], parts[2]), os.path.join(PARTS, name)))
    assert files, "no parts found"

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mod.json", json.dumps(MOD, indent=2) + "\n")
        for arcname, path in sorted(files):
            z.write(path, arcname)
    print("built %s  %d bytes  %d overlays" % (OUT, os.path.getsize(OUT), len(files)))
    for arcname, _ in sorted(files):
        print("   %s" % arcname)

    game_dir = paths.option("--game-dir", "TP_GAME_DIR")
    if not game_dir:
        return
    game_mods = os.path.join(game_dir, "data", "mods")
    os.makedirs(game_mods, exist_ok=True)
    dst = os.path.join(game_mods, "cn_text_sjis.dusk")
    with open(OUT, "rb") as a, open(dst, "wb") as b:
        b.write(a.read())
    print("installed -> %s" % dst)

    config = os.path.join(game_dir, "data", "config.json")
    with open(config, encoding="utf-8") as f:
        cfg = json.load(f)
    for key in DISABLE:
        cfg[key] = False
    cfg[ENABLE] = True
    cfg["game.enableChineseNameKeyboard"] = True
    with open(config, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)
    print("config: %s = True, game.enableChineseNameKeyboard = True, others off" % ENABLE)


main()
