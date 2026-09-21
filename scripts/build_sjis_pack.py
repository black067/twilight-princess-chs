import json
import os
import re
import struct
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

# mod.json 的文本字段：顺序即包内键序（客户端 manifest.cpp 按名字取，顺序无要求，
# 但固定成 id→name→version→author→description→icon→banner，方便与包内内容对拍）。
TEXT_FIELDS = ("id", "name", "version", "author", "description")

# icon / banner：config 里填**本地 PNG 路径**，包内固定放这两个路径（客户端找不到 manifest
# 里的路径时会自动回退到 res/icon.png、res/banner.png；站点也从包里取图）。
IMAGE_FIELDS = {"icon": "res/icon.png", "banner": "res/banner.png"}

# 本地闸门：站点已收录 22 个 mod 的 summary（= mod.json 的 description）最长 265、全部单行无链接。
# 只有长度当硬限制，换行/链接只提示。
MAX_NAME = 48
MAX_DESCRIPTION = 265
# 客户端 utils::is_valid_mod_id：小写字母/数字/下划线/点，首尾不能是点、不能有连续点（单段也合法）
MOD_ID_RE = re.compile(r"^[a-z0-9_.]+$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)


def fill_slot(text, region, language):
    """展开 name/description 里的占位符：{region} / {language} / {repo}。"""
    repo = str(paths.config_value("repo") or "")
    if "{repo}" in text and not repo:
        print("警告：描述里用了 {repo}，但 config.json 没配 repo", file=sys.stderr)
    return (text.replace("{region}", SLOT_NAMES["region"][region])
                .replace("{language}", SLOT_NAMES["language"][language])
                .replace("{repo}", repo))


def select_fields(meta, variant):
    """取要处理的字段；config 段里的内部键不进包（icon/banner 是本地路径，打包时换成包内路径）。"""
    known = set(TEXT_FIELDS) | set(IMAGE_FIELDS)
    extra = sorted(set(meta) - known)
    if extra:
        print("提示：%s 里的 %s 不进 mod.json" % (variant, ", ".join(extra)))
    return {key: meta[key] for key in TEXT_FIELDS + tuple(IMAGE_FIELDS) if key in meta}


def check_meta(meta):
    """本地闸门：站点会拒的问题挡在打包之前，其余只提示（站点只回一句笼统报错）。"""
    problems, warnings = [], []

    def text(key):
        value = meta.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append("%s：缺字段或不是字符串" % key)
            return ""
        return value

    mod_id, name, version = text("id"), text("name"), text("version")
    author, description = text("author"), text("description")

    if mod_id and (not MOD_ID_RE.match(mod_id) or mod_id[0] == "." or mod_id[-1] == "."
                   or ".." in mod_id):
        problems.append("id：只能小写字母/数字/下划线/点，首尾不能是点、不能有连续点，现在 %r"
                        % mod_id)
    elif mod_id and "." not in mod_id:
        warnings.append("id：不含点；站点示例都是反向域名（com.<作者>.<名字>）")
    if len(name) > MAX_NAME:
        problems.append("name：%d 字符 > %d" % (len(name), MAX_NAME))
    if version and not VERSION_RE.match(version):
        problems.append("version：要 X.Y.Z，现在 %r" % version)
    if len(description) > MAX_DESCRIPTION:
        problems.append("description：%d 字符 > %d（站点已收录最长的 summary）"
                        % (len(description), MAX_DESCRIPTION))
    for key, value in (("name", name), ("author", author), ("description", description)):
        if "\n" in value or "\r" in value:
            warnings.append("%s：含换行；站点只收录单行摘要，长文放页面正文" % key)
    if URL_RE.search(description):
        warnings.append("description：含链接；链接放站点的 Source 字段")

    for line in warnings:
        print("  提示：%s" % line, file=sys.stderr)
    if problems:
        for line in problems:
            print("  - %s" % line, file=sys.stderr)
        sys.exit("元数据没通过本地校验：改 %s 里的 mod / mod_ique" % paths.CONFIG_EXAMPLE)


def print_meta(meta):
    """打包前把最终写进包的字段和长度打出来。"""
    print("   id          %s" % meta.get("id"))
    print("   name        %s  (%d)" % (meta.get("name"), len(str(meta.get("name", "")))))
    print("   version     %s" % meta.get("version"))
    print("   author      %s" % meta.get("author"))
    print("   description %s  (%d)"
          % (meta.get("description"), len(str(meta.get("description", "")))))


def png_size(path):
    """PNG 的 (宽, 高)；不是 PNG 返回 None。"""
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return struct.unpack_from(">II", head, 16)


def collect_images(meta):
    """config 里的 icon/banner 源图 -> [(字段, 包内路径, 本地路径)]。

    包内固定放 res/<字段>.png（客户端会在 manifest 路径不可用时回退到这两个路径，
    站点也从包里取图）；没配就什么都不做，站点列表显示首字母占位。
    """
    out = []
    for key, arcname in IMAGE_FIELDS.items():
        value = meta.get(key)
        if not value:
            continue
        src = str(value)
        if not os.path.isabs(src):
            src = os.path.join(paths.ROOT, src)
        if not os.path.isfile(src):
            sys.exit("%s 指定的图片不存在：%s" % (key, src))
        size = png_size(src)
        if size is None:
            sys.exit("%s 只收 PNG：%s" % (key, src))
        print("   %-8s %s  %dx%d" % (key, src, size[0], size[1]))
        if key == "icon" and size[0] != size[1]:
            print("  提示：icon 建议 1:1", file=sys.stderr)
        if key == "banner" and size[0] < 800:
            print("  提示：banner 建议宽 ≥ 800、约 3.5:1", file=sys.stderr)
        out.append((key, arcname, src))
    if not out:
        print("  提示：没配 icon/banner，站点列表显示首字母占位"
              "（在 config 的这段里填本地 PNG 路径）", file=sys.stderr)
    return out


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


def build(variant, meta, region, language, out_dir, check_only=False):
    """打一个变体：meta 就是 config 里那一段，字库部件按变体取。"""
    meta = select_fields(meta, variant)
    meta["name"] = fill_slot(str(meta.get("name", "")), region, language)
    meta["description"] = fill_slot(str(meta.get("description", "")), region, language)
    print("== %s 变体 ==" % variant)
    print_meta(meta)
    check_meta(meta)
    images = collect_images(meta)      # --check 也过一遍图片（存在性 + PNG 尺寸）
    if check_only:
        return None

    font_parts = paths.parts_dir(variant)
    if not os.path.isdir(font_parts):
        sys.exit("缺 %s 变体的字库部件：先跑 patch_sjis_font.py（%s）" % (variant, font_parts))
    fonts = collect(font_parts, want_font=True)
    files = sorted(collect(TEXT_PARTS, want_font=False) + fonts)
    assert files, "no parts found in %s" % TEXT_PARTS
    assert len(fonts) == 2, "%s 里应有 2 个字体部件，实际 %d" % (font_parts, len(fonts))

    entries = [(arcname, src) for _, arcname, src in images] + files
    for key, arcname, _ in images:
        meta[key] = arcname             # manifest 里写包内路径

    out = os.path.join(out_dir, paths.escape_mod_id(meta["id"]) + ".dusk")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        # 字节格式：2 空格缩进、键序 id→…→banner、末尾不留换行、UTF-8 无 BOM
        z.writestr("mod.json", json.dumps(meta, indent=2, ensure_ascii=False))
        for arcname, path in entries:
            z.write(path, arcname)
    print("built %s  %d bytes  id=%s  字库部件来自 %s"
          % (out, os.path.getsize(out), meta["id"], os.path.basename(font_parts)))
    for arcname, _ in entries:
        print("   %s" % arcname)
    return out


def main():
    check_only = "--check" in sys.argv
    region, language = paths.slot()
    out_dir = paths.config_dir("out", os.path.join("work", "mods"))
    os.makedirs(out_dir, exist_ok=True)
    if os.path.isdir(TEXT_PARTS):
        other = sorted({p[1] for p in (e.split("_", 2) for e in os.listdir(TEXT_PARTS))
                        if len(p) == 3 and p[0] == "res"} - {paths.font_dir(), paths.msg_dir()})
        if other:
            print("提示：部件里还有非当前槽位的目录：%s" % ", ".join(other))
    elif not check_only:
        sys.exit("缺文本部件：先跑 patch_sjis_text.py（%s）" % TEXT_PARTS)

    for variant, key in paths.VARIANTS:
        meta = paths.config_value(key)
        if not isinstance(meta, dict):
            sys.exit("%s 里缺 %s 段（id/name/description）" % (paths.CONFIG_EXAMPLE, key))
        build(variant, meta, region, language, out_dir, check_only)
    if check_only:
        print("--check：只校验元数据，没写包")
    else:
        print("上传前手工项：Category / License / Source URL / 截图 / changelog（站点后台填）")


main()
