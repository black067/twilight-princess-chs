import json
import os
import sys
import zipfile

import paths

# 文本部件（两个变体共用）写在 open 变体的目录里
TEXT_PARTS = paths.parts_dir("open")

# name/description 里 {region} / {language} / {repo} 的展开（写给玩家看）
SLOT_NAMES = {
    "region": {"us": "United States", "eu": "Europe", "jp": "Japan"},
    "language": {"us": "English (US)", "uk": "English (UK)", "de": "German", "fr": "French",
                 "sp": "Spanish", "it": "Italian", "jp": "Japanese"},
}


def fill_slot(text, region, language):
    """展开 name/description 里的占位符：{region} / {language} / {repo}。"""
    repo = str(paths.config_value("repo") or "")
    if "{repo}" in text and not repo:
        print("警告：描述里用了 {repo}，但 config.json 没配 repo", file=sys.stderr)
    return (text.replace("{region}", SLOT_NAMES["region"][region])
                .replace("{language}", SLOT_NAMES["language"][language])
                .replace("{repo}", repo))


def collect(dir_path, want_font):
    """目录里的部件 -> [(zip 内路径, 文件路径)]；want_font 区分字库/文本槽。"""
    out = []
    for entry in sorted(os.listdir(dir_path)):
        parts = entry.split("_", 2)
        if len(parts) != 3 or parts[0] != "res":
            continue
        if (parts[1] == paths.font_dir()) != want_font:
            continue
        out.append(("overlay/res/%s/%s" % (parts[1], parts[2]), os.path.join(dir_path, entry)))
    return out


def build(variant, meta, region, language, out_dir):
    """打一个变体：meta 就是 config 里那一段，字库部件按变体取。"""
    if not meta.get("id"):
        sys.exit("%s 里缺 %s.id" % (paths.CONFIG_EXAMPLE, variant))
    font_parts = paths.parts_dir(variant)
    if not os.path.isdir(font_parts):
        sys.exit("缺 %s 变体的字库部件：先跑 patch_sjis_font.py（%s）" % (variant, font_parts))
    fonts = collect(font_parts, want_font=True)
    files = sorted(collect(TEXT_PARTS, want_font=False) + fonts)
    assert files, "no parts found in %s" % TEXT_PARTS
    assert len(fonts) == 2, "%s 里应有 2 个字体部件，实际 %d" % (font_parts, len(fonts))

    meta = dict(meta)
    meta["name"] = fill_slot(str(meta.get("name", "")), region, language)
    meta["description"] = fill_slot(str(meta.get("description", "")), region, language)
    out = os.path.join(out_dir, paths.escape_mod_id(meta["id"]) + ".dusk")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mod.json", json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
        for arcname, path in files:
            z.write(path, arcname)
    print("built %s  %d bytes  id=%s  字库部件来自 %s"
          % (out, os.path.getsize(out), meta["id"], os.path.basename(font_parts)))
    for arcname, _ in files:
        print("   %s" % arcname)
    return out


def main():
    region, language = paths.slot()
    out_dir = paths.config_dir("out", os.path.join("work", "mods"))
    os.makedirs(out_dir, exist_ok=True)
    if not os.path.isdir(TEXT_PARTS):
        sys.exit("缺文本部件：先跑 patch_sjis_text.py（%s）" % TEXT_PARTS)
    other = sorted({p[1] for p in (e.split("_", 2) for e in os.listdir(TEXT_PARTS))
                    if len(p) == 3 and p[0] == "res"} - {paths.font_dir(), paths.msg_dir()})
    if other:
        print("提示：部件里还有非当前槽位的目录：%s" % ", ".join(other))

    for variant, key in paths.VARIANTS:
        meta = paths.config_value(key)
        if not isinstance(meta, dict):
            sys.exit("%s 里缺 %s 段（id/name/description）" % (paths.CONFIG_EXAMPLE, key))
        build(variant, meta, region, language, out_dir)


main()
