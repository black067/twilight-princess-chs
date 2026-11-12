"""合并包：一个 .dusk 同时带多种译文，玩家在 mod 面板里选译文与游戏语言。

资源放 res/<译文>/，运行时由 res/main.luau 按配置项注册 overlay；包内没有 overlay/ 目录。
产物 dist/<转义 id>.dusk，元信息与站点限制的校验复用 build_pack。
"""

import json
import os
import sys
import zipfile

import build_pack
import paths

RUNTIME = "dev.twilitrealm.luau@1.0"
TEMPLATE = os.path.join(paths.HERE, "luau", "main.luau")
OPTIONS_ENTRY = "res/options.luau"
MAIN_ENTRY = "res/main.luau"


def lua_string(value):
    out = ['"']
    for ch in str(value):
        if ch in ('"', "\\"):
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append("\\%d" % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def translations():
    """[(config 里的语言名, 面板标签)]：按配置顺序，校验语言存在且不重复。"""
    raw = paths.bundle_value("translations")
    if not isinstance(raw, list) or not raw:
        sys.exit("%s 里缺 bundle.translations（每项 {lang, label}）" % paths.CONFIG_DEFAULT)
    known = paths._langs()
    out, seen = [], set()
    for item in raw:
        item = item or {}
        name = str(item.get("lang") or "")
        label = str(item.get("label") or "")
        if name not in known:
            sys.exit("bundle.translations 里的 lang 不在 langs 里：%r" % name)
        if not label:
            sys.exit("bundle.translations 的 %s 缺 label" % name)
        if name in seen:
            sys.exit("bundle.translations 里 %s 重复" % name)
        seen.add(name)
        out.append((name, label))
    return out


def bundle_assets(name):
    """该译文的 (字库文件名, 消息文件名, [文件路径])；缺文件直接报错。"""
    space = paths.DEFAULT_CODE_SPACE
    fonts = paths.font_parts(paths.OPEN_VARIANT, space, name)
    for filename, path in fonts:
        if not os.path.exists(path):
            sys.exit("缺字库资源 %s：先跑 python scripts\\build_bfn.py --lang %s" % (path, name))
    texts = paths.text_parts(paths.OPEN_VARIANT, space, name)
    if not texts:
        sys.exit("缺文本资源：先跑 python scripts\\build_bmg.py --lang %s" % name)
    paths.check_manifest(paths.parts_dir(paths.OPEN_VARIANT, space, name),
                         paths.OPEN_VARIANT, space)
    return ([filename for filename, _path in fonts],
            [filename for filename, _path in texts],
            [path for _filename, path in fonts] + [path for _filename, path in texts])


def font_regions():
    raw = paths.bundle_value("font_regions")
    if not isinstance(raw, list) or not raw:
        sys.exit("%s 里缺 bundle.font_regions（字库写进哪些 Font<region>）" % paths.CONFIG_DEFAULT)
    out = [str(item).lower() for item in raw]
    for region in out:
        if region not in paths.REGIONS:
            sys.exit("bundle.font_regions 里的 %r 无效（可选 %s）"
                     % (region, " / ".join(paths.REGIONS)))
    return out


def defaults(keys, codes):
    translation = str(paths.bundle_value("default_translation") or "")
    if translation not in keys:
        sys.exit("bundle.default_translation = %r 不在 translations 里" % translation)
    raw = paths.bundle_value("default_locales")
    if not isinstance(raw, list) or not raw:
        sys.exit("%s 里缺 bundle.default_locales（默认选中的游戏语言）" % paths.CONFIG_DEFAULT)
    locales = [str(item).lower() for item in raw]
    for code in locales:
        if code not in codes:
            sys.exit("bundle.default_locales 里的 %r 不在 locales 里" % code)
    return translation, ",".join(locales)


def ui_text():
    ui = paths.bundle_value("ui") or {}
    keys = ("label_translation", "section_locale", "hint")
    missing = [key for key in keys if not str(ui.get(key) or "").strip()]
    if missing:
        sys.exit("%s 的 bundle.ui 里缺 %s" % (paths.CONFIG_DEFAULT, " / ".join(missing)))
    return {key: str(ui[key]) for key in keys}


def options_source(items, default_translation, default_locales, regions, font_files, msg_files, ui):
    """生成 res/options.luau：纯数据表，主脚本按它拼 overlay。"""
    lines = ["return {", "    translations = {"]
    for index, (name, label) in enumerate(items):
        lines.append("        { key = %s, label = %s, offset = %d },"
                     % (lua_string(name), lua_string(label), index))
    lines.append("    },")
    lines.append("    translation_by_offset = {")
    for index, (name, _label) in enumerate(items):
        lines.append("        [%s] = %s," % (lua_string(str(index)), lua_string(name)))
    lines.append("    },")
    lines.append("    default_translation = %s," % lua_string(default_translation))
    lines.append("    locales = {")
    for code, label, _region in paths.locales():
        lines.append("        { code = %s, label = %s }," % (lua_string(code), lua_string(label)))
    lines.append("    },")
    lines.append("    default_locales = %s," % lua_string(default_locales))
    lines.append("    font_regions = { %s },"
                 % ", ".join(lua_string(region) for region in regions))
    lines.append("    font_files = { %s },"
                 % ", ".join(lua_string(name) for name in font_files))
    lines.append("    msg_files = { %s },"
                 % ", ".join(lua_string(name) for name in msg_files))
    lines.append("    ui = {")
    for key in ("label_translation", "section_locale", "hint"):
        lines.append("        %s = %s," % (key, lua_string(ui[key])))
    lines.append("    },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def build(check_only=False):
    meta = build_pack.select_fields(paths.bundle_value("meta") or {}, "bundle")
    items = translations()
    keys = [name for name, _label in items]
    print("== 合并包：%s 种译文 ==" % len(items))
    build_pack.print_meta(meta)
    build_pack.check_meta(meta, ["bundle.meta"])
    images = build_pack.collect_images(meta)

    codes = paths.locale_codes()
    default_translation, default_locales = defaults(keys, codes)
    regions = font_regions()
    ui = ui_text()

    assets = {}
    font_files, msg_files = None, None
    for name in keys:
        fonts, texts, files = bundle_assets(name)
        if font_files is None:
            font_files, msg_files = fonts, texts
        elif (fonts, texts) != (font_files, msg_files):
            sys.exit("译文 %s 的资源清单与 %s 不一致：%r / %r" % (name, keys[0], fonts, texts))
        assets[name] = files

    options = options_source(items, default_translation, default_locales, regions,
                             font_files, msg_files, ui)
    print("   默认 %s + %s，字库写 %s" % (default_translation, default_locales, "/".join(regions)))
    if check_only:
        return None

    with open(TEMPLATE, encoding="utf-8") as f:
        main_source = f.read()

    for key, arcname, _ in images:
        meta[key] = arcname
    meta["runtime"] = RUNTIME

    out = os.path.join(paths.out_dir(), paths.escape_mod_id(meta["id"]) + ".dusk")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        build_pack.add_bytes(z, "mod.json",
                             json.dumps(meta, indent=2, ensure_ascii=False).encode("utf-8"))
        for _key, arcname, src in images:
            build_pack.add_file(z, src, arcname)
        build_pack.add_bytes(z, MAIN_ENTRY, main_source.encode("utf-8"))
        build_pack.add_bytes(z, OPTIONS_ENTRY, options.encode("utf-8"))
        for name in keys:
            for src in assets[name]:
                build_pack.add_file(z, src, "res/%s/%s" % (name, os.path.basename(src)))

    print("built %s  %d bytes  id=%s" % (out, os.path.getsize(out), meta["id"]))
    print("   mod.json")
    print("   %s" % MAIN_ENTRY)
    print("   %s" % OPTIONS_ENTRY)
    for _key, arcname, _src in images:
        print("   %s" % arcname)
    for name in keys:
        print("   res/%s/  %d 个资源" % (name, len(assets[name])))
    return out


def main():
    check_only = "--check" in sys.argv
    os.makedirs(paths.out_dir(), exist_ok=True)
    build(check_only)
    if check_only:
        print("--check：只校验配置与资源，没写包")
    else:
        print("上传前手工项：Category / License / Source URL / 截图 / changelog（站点后台填）")


if __name__ == "__main__":
    main()
