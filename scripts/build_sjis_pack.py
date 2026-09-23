import json
import os
import re
import struct
import sys
import zipfile

import paths

# name/description/id 里 {region} / {language} / {repo} 的展开在 paths.expand

# mod.json 的文本字段：顺序即包内字段顺序（客户端 manifest.cpp 按名字取，顺序无要求，
# 但固定成 id→name→version→author→description→icon→banner，方便与包内内容对拍）。
TEXT_FIELDS = ("id", "name", "version", "author", "description")

# icon / banner：config 里填**本地 PNG 路径**，包内固定放这两个路径（客户端找不到 manifest
# 里的路径时会自动回退到 res/icon.png、res/banner.png；站点也从包里取图）。
IMAGE_FIELDS = {"icon": "res/icon.png", "banner": "res/banner.png"}

# 站点侧限制：只有长度当硬限制，换行/链接只提示。
MAX_NAME = 48
MAX_DESCRIPTION = 265
MOD_ID_RE = re.compile(r"^[a-z0-9_.]+$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)


# 缺资源时提示该先跑哪个脚本（按变体）
FONT_STEP = {paths.OPEN_VARIANT: "build_bfn.py", paths.ORIGIN_VARIANT: "patch_sjis_font.py"}
TEXT_STEP = {paths.OPEN_VARIANT: "build_bmg.py", paths.ORIGIN_VARIANT: "patch_sjis_text.py"}


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
        sys.exit("元数据没通过本地校验：改 %s 里的 %s"
                 % (paths.CONFIG_DEFAULT, " / ".join(key for _, key in paths.VARIANTS)))


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


def overlay_entries(variant, region, language):
    """资源 -> [(zip 内路径, 文件路径)]：字库写进 Font<region>，消息写进 Msg<language>。"""
    fonts = paths.font_parts(variant)
    for name, path in fonts:
        if not os.path.exists(path):
            sys.exit("缺字库资源 %s：先跑 %s" % (path, FONT_STEP[variant]))
    texts = paths.text_parts(variant)
    if not texts:
        sys.exit("缺文本资源：先跑 %s（%s）" % (TEXT_STEP[variant], paths.parts_dir(variant)))
    return ([("overlay/res/%s/%s" % (paths.font_dir(region), n), p) for n, p in fonts]
            + [("overlay/res/%s/%s" % (paths.msg_dir(language), n), p) for n, p in texts])


# zip 成员时间戳固定：同一份输入必须打出同一个包字节，否则打包时间进了产物、文件 sha256 就不能当回归的比对依据
STAMP = (1980, 1, 1, 0, 0, 0)


def add_bytes(z, arcname, data):
    info = zipfile.ZipInfo(arcname, STAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    z.writestr(info, data)


def add_file(z, path, arcname):
    with open(path, "rb") as f:
        add_bytes(z, arcname, f.read())


def build(variant, meta, region, language, out_dir, check_only=False):
    """打一个变体在一个地区的包。"""
    meta = select_fields(meta, variant)
    print("== %s：%s 变体 / %s 盘 ==" % (paths.lang(), variant, region))
    print_meta(meta)
    check_meta(meta)
    images = collect_images(meta)      # --check 也过一遍图片（存在性 + PNG 尺寸）
    if check_only:
        return None

    files = sorted(overlay_entries(variant, region, language))
    entries = [(arcname, src) for _, arcname, src in images] + files
    for key, arcname, _ in images:
        meta[key] = arcname             # manifest 里写包内路径

    out = os.path.join(out_dir, paths.escape_mod_id(meta["id"]) + ".dusk")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        # 字节格式：2 空格缩进、字段顺序 id→…→banner、末尾不留换行、UTF-8 无 BOM
        add_bytes(z, "mod.json", json.dumps(meta, indent=2, ensure_ascii=False).encode("utf-8"))
        for arcname, path in entries:
            add_file(z, path, arcname)
    print("built %s  %d bytes  id=%s  字库资源来自 %s"
          % (out, os.path.getsize(out), meta["id"], paths.PARTS_DIR[variant]))
    for arcname, _ in entries:
        print("   %s" % arcname)
    return out


def main():
    check_only = "--check" in sys.argv
    region_filter = paths.cli("--region")
    variant_filter = paths.cli("--variant")
    discs = [d for d in paths.discs() if not region_filter or d[0] == region_filter]
    if not discs:
        sys.exit("--region %s 不在配置的 discs 里（%s）"
                 % (region_filter, " / ".join(r for r, _ in paths.discs())))
    variants = [v for v, _ in paths.VARIANTS if not variant_filter or v == variant_filter]
    if not variants:
        sys.exit("--variant 只支持 %s" % " / ".join(v for v, _ in paths.VARIANTS))
    if not variant_filter:
        # 不带 --variant 时只打 PUBLISHED_VARIANTS，其余变体要显式指定
        variants = [v for v in variants if v in paths.PUBLISHED_VARIANTS]
        print("只打 %s（其余用 --variant 指定）" % " / ".join(variants))

    out_dir = paths.out_dir()
    os.makedirs(out_dir, exist_ok=True)
    jobs = [(v, r, l, paths.mod_meta(v, r, l)) for r, l in discs for v in variants]
    ids = [m["id"] for *_, m in jobs]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        sys.exit("mod id 重复（id 模板里要有 {region}）：%s" % ", ".join(dup))

    for variant, region, language, meta in jobs:
        build(variant, meta, region, language, out_dir, check_only)
    if check_only:
        print("--check：只校验元数据，没写包")
    else:
        print("上传前手工项：Category / License / Source URL / 截图 / changelog（站点后台填）")


main()
