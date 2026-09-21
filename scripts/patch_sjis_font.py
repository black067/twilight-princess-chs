import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import bfn_repack as R
import font_render as font
import paths
import yaz0
from build_cn_font import patch_rarc, repack_bfn, yaz0_encode
from extract_entry import extract
from extract_index import HEADER_LEN, decrypt_region
from list_index import entries

MAP_JSON = os.path.join(paths.WORK, "sjis_map.json")
NAME_KEYBOARD = os.path.join(paths.DATA, "name_keyboard.json")
KB_JSON = os.path.join(paths.WORK, "keyboard_aliases.json")
OUT_DIR = os.path.join(paths.WORK, "sjis_parts")

FONT_SLOTS = {
    "res/Fontcn/fontres.arc": "res/%s/fontres.arc" % paths.font_dir(),
    "res/Fontcn/rubyres.arc": "res/%s/rubyres.arc" % paths.font_dir(),
}

SHIFT_JIS_FONT_TYPE = 2

# 引擎在非日版下会为 group-6 图标 tag 插入 1 字节码位（d_msg_class.cpp 的 CHAR_CODE_*）。
# 这些码位在原字库里对应图标字形；本字库（** CN）没有它们，改成指向等价的符号字形。
ICON_ALIAS = {
    0x00B1: 0x2605,  # STAR_ICON          -> ★
    0x00B2: 0x2642,  # MALE_ICON          -> ♂
    0x00B3: 0x2640,  # FEMALE_ICON        -> ♀
    0x00B9: 0x2190,  # THIN_LEFT_ARROW    -> ←
    0x00BC: 0x2192,  # THIN_RIGHT_ARROW   -> →
    0x00BD: 0x2191,  # THIN_UP_ARROW      -> ↑
    0x00BE: 0x2193,  # THIN_DOWN_ARROW    -> ↓
}

# 名字键盘（l_mojiZh）原表里 157 格是** CN 字库没收的日式写法/生僻字。
# 下面这 55 格是日式新字体，对应的简体字在字库里，用简体替代；其余 102 格没有字形，
# 指向空白字形，免得引擎去查一个不存在的码位。
NAME_VARIANT = {
    "亜": "亚", "愛": "爱", "偉": "伟", "為": "为", "隠": "隐", "鰻": "鳗", "運": "运",
    "営": "营", "開": "开", "階": "阶", "該": "该", "鈎": "钩", "嚇": "吓", "撹": "搅",
    "獲": "获", "渇": "渴", "轄": "辖", "寛": "宽", "機": "机", "軌": "轨", "騎": "骑",
    "亀": "龟", "義": "义", "喫": "吃", "給": "给", "強": "强", "倶": "俱", "係": "系",
    "経": "经", "撃": "击", "訣": "诀", "捲": "卷", "顕": "显", "誤": "误", "構": "构",
    "購": "购", "砿": "矿", "項": "项", "賛": "赞", "斬": "斩", "師": "师", "糸": "丝",
    "賜": "赐", "児": "儿", "爾": "尔", "車": "车", "衆": "众", "縦": "纵", "術": "术",
    "処": "处", "傷": "伤", "償": "偿", "勝": "胜", "紹": "绍", "乗": "乘",
}


def name_keyboard_aliases(orig_glyph, free_slots=(), tail_slots=(), open_mode=False):
    """引擎名字键盘字表（l_mojiZh）逐格别名。

    原字不在字库的：55 个日式写法换成对应简体字；其余格在 open 模式分配
    空槽/tail 槽用渲染字形补全，original 模式保持指向空白字形（U+3000）。
    返回 (aliases, new_chars, stats)：new_chars = {新槽: 字符}（待渲染）。
    """
    with open(NAME_KEYBOARD, encoding="utf-8") as f:
        doc = json.load(f)
    table = [int(c, 16) for c in doc["codes"]]
    blank = orig_glyph[0x3000]
    free = list(free_slots)
    tail = list(tail_slots)
    aliases = []
    new_chars = {}
    assigned = {}
    direct = variant = blanked = added = 0
    for code in table:
        char = bytes((code >> 8, code & 0xFF)).decode("shift_jis")
        glyph = orig_glyph.get(ord(char))
        if glyph is not None:
            direct += 1
        else:
            target = NAME_VARIANT.get(char)
            glyph = orig_glyph.get(ord(target)) if target else None
            if glyph is not None:
                variant += 1
            elif open_mode:
                glyph = assigned.get(char)
                if glyph is None:
                    if free:
                        glyph = free.pop(0)
                    elif tail:
                        glyph = tail.pop(0)
                    else:
                        sys.exit("键盘补全缺少可用槽位")
                    assigned[char] = glyph
                    new_chars[glyph] = char
                added += 1
            else:
                glyph = blank
                blanked += 1
        aliases.append((code, glyph))
    print("   名字键盘别名: %d 格 (原字 %d / 换简体 %d / 补全渲染 %d / 空白 %d)"
          % (len(aliases), direct, variant, added, blanked))
    return aliases, new_chars, (direct, variant, blanked, added)


def add_aliases(body, blocks, orig_glyph, remap, kb_aliases):
    target = None
    for b in blocks:
        if b[0] == b"MAP1" and struct.unpack_from(">H", body, b[1] + 0x08)[0] == 3:
            target = b
    assert target is not None, "no method-3 MAP1 block"
    off, size = target[1], target[2]
    num = struct.unpack_from(">H", body, off + 0x0E)[0]
    entries = []
    for k in range(num):
        old_code, idx = struct.unpack_from(">HH", body, off + 0x10 + k * 4)
        entries.append((remap.get(old_code, old_code), idx))
    for icon, char in ICON_ALIAS.items():
        glyph = orig_glyph.get(char)
        assert glyph is not None, "icon target glyph missing: %#x" % char
        entries.append((icon, glyph))
    entries += kb_aliases
    entries.sort()
    assert len({c for c, _ in entries}) == len(entries), "duplicate code after alias"
    table = b"".join(struct.pack(">HH", c, i) for c, i in entries)
    block = struct.pack(">4sIHHHH", b"MAP1", 0x10 + len(table), 3,
                        entries[0][0], entries[-1][0], len(entries)) + table
    out = bytearray(body[:0x20])
    for magic, boff, bsize in blocks:
        out += block if (magic, boff, bsize) == target else body[boff : boff + bsize]
    struct.pack_into(">I", out, 0x08, len(out))
    print("   图标别名: +%d 条, MAP1 表 %d 条, 码位 %#x..%#x"
          % (len(ICON_ALIAS), len(entries), entries[0][0], entries[-1][0]))
    return bytes(out)


def main():
    with open(MAP_JSON, encoding="utf-8") as f:
        doc = json.load(f)
    remap = {int(k, 16): int(v, 16) for k, v in doc["remap"].items()}

    source = paths.option("--glyph-source") or "original"
    ttf = None
    if source != "original":
        if not source.startswith("open"):
            sys.exit("--glyph-source 只支持 original 或 open[:<ttf>]：%s" % source)
        ttf = source.split(":", 1)[1] if ":" in source else paths.option("--cn-font")
        if not ttf or not os.path.exists(ttf):
            sys.exit("open 模式需要字体文件：--glyph-source open:<ttf>，或在 config.json 配 cn_font")
    em = float(paths.option("--em") or font.DEFAULT_EM)

    pak = paths.pak()
    with open(pak, "rb") as f:
        head = f.read(HEADER_LEN)
        size1 = struct.unpack_from("<I", head, 0x18)[0]
        index = decrypt_region(f, HEADER_LEN, size1, "header")
    recs = entries(index)
    data_start = HEADER_LEN + len(index)
    os.makedirs(OUT_DIR, exist_ok=True)

    renderer = font.Renderer(ttf) if ttf else None
    kb_tables = {}
    try:
        for src, dst in FONT_SLOTS.items():
            r = next(x for x in recs if x[0] == src)
            arc = yaz0.decompress(extract(pak, data_start, src, r[1], r[3]))
            start, bfn, blocks = R.parse_bfn(arc)
            bfn_size = struct.unpack_from(">I", bfn, 0x08)[0]
            print("== %s bfn@%#x size=%d" % (src, start, bfn_size))

            packed = repack_bfn(bfn[:bfn_size])
            _, _, blocks = R.parse_bfn(packed)
            arc2 = bytearray(packed)

            inf = next(b for b in blocks if b[0] == b"INF1")
            old_type = struct.unpack_from(">H", arc2, inf[1] + 0x08)[0]
            struct.pack_into(">H", arc2, inf[1] + 0x08, SHIFT_JIS_FONT_TYPE)
            print("   INF1 fontType %d -> %d" % (old_type, SHIFT_JIS_FONT_TYPE))

            target = next(b for b in blocks
                          if b[0] == b"MAP1" and struct.unpack_from(">H", arc2, b[1] + 0x08)[0] == 3)
            num = struct.unpack_from(">H", arc2, target[1] + 0x0E)[0]
            orig_glyph = {}
            for k in range(num):
                code, idx = struct.unpack_from(">HH", arc2, target[1] + 0x10 + k * 4)
                orig_glyph[code] = idx
            print("   MAP1 源表 entries=%d  codes %#x..%#x  glyph max %#x"
                  % (num, min(orig_glyph), max(orig_glyph), max(orig_glyph.values())))

            m0 = []
            for b in blocks:
                if b[0] == b"MAP1" and struct.unpack_from(">H", arc2, b[1] + 0x08)[0] == 0:
                    m0.append(struct.unpack_from(">HH", arc2, b[1] + 0x0A))

            g = next(b for b in blocks if b[0] == b"GLY1")
            fields = R.gly1_fields(arc2, g[1])
            total = fields["endCode"] - fields["startCode"]
            used = set(orig_glyph.values()) | {c - sc for sc, ec in m0 for c in range(sc, ec + 1)}
            free = sorted(set(range(total)) - used)
            tail = list(range(total, fields["numRows"] * fields["numColumns"]))
            kb_aliases, new_chars, kb_stats = name_keyboard_aliases(
                orig_glyph, free, tail, open_mode=bool(renderer))

            if renderer and new_chars:
                end_code = None
                over = [i for i in new_chars if i >= total]
                if over:
                    end_code = max(over) + 1
                    limit = fields["numRows"] * fields["numColumns"]
                    assert end_code <= limit, "键盘补全超出图集容量：%d > %d" % (end_code, limit)
                roster, _ = font.build_roster(orig_glyph, m0)
                roster.update(new_chars)
                missing = font.check_coverage(font.parse_cmap(ttf), roster)
                if missing:
                    for idx, ch, cp in missing[:20]:
                        print("   缺字 槽 %#x 码位 U+%04X %r" % (idx, cp, ch))
                    sys.exit("名册含字体缺失字符 %d 个（不允许静默缺字）" % len(missing))
                bboxes, _ = font.scan_bboxes(bytes(arc2), sorted(roster))
                inf1 = font.read_inf1(bytes(arc2))
                atlas, rstats = font.render_atlas(
                    renderer, roster, fields, em=em, bboxes=bboxes,
                    baseline=inf1["ascent"] if inf1 else font.DEFAULT_BASELINE)
                print("   渲染 %d 字（继承 %d / 基线 %d / 缩放充入 %d / 裁剪 %d / 空 %d）endCode=%s"
                      % (rstats["rendered"], rstats["inherit"], rstats["fallback"],
                         rstats["rescaled"], rstats["clipped"], rstats["blank"],
                         ("%#x" % end_code) if end_code else "不变"))
                arc2 = bytearray(font.overwrite_gly1(bytes(arc2), atlas, end_code))
                _, _, blocks = R.parse_bfn(bytes(arc2))

            new_bfn = add_aliases(bytes(arc2), blocks, orig_glyph, remap, kb_aliases)
            new_arc = patch_rarc(arc, start, new_bfn)
            path = os.path.join(OUT_DIR, dst.replace("/", "_"))
            with open(path, "wb") as f:
                f.write(yaz0_encode(new_arc))
            print("   wrote %s (arc %d -> %d bytes, yaz0 %d bytes)"
                  % (os.path.basename(path), len(arc), len(new_arc), os.path.getsize(path)))
            kb_tables[os.path.splitext(os.path.basename(dst))[0]] = {
                "aliases": [["%04X" % c, "%04X" % i] for c, i in kb_aliases],
                "new_chars": {"%04X" % i: ch for i, ch in sorted(new_chars.items())},
                "direct": kb_stats[0], "variant": kb_stats[1],
                "added": kb_stats[3], "blanked": kb_stats[2],
            }
    finally:
        if renderer:
            renderer.close()

    with open(KB_JSON, "w", encoding="utf-8") as f:
        json.dump(kb_tables, f, ensure_ascii=False, indent=1)
    print("wrote %s" % KB_JSON)


if __name__ == "__main__":
    main()
