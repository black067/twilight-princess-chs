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


# 引擎自带名字键盘（上游 d_name.cpp 的 l_mojiEisuPal_1/2，EU 版）里，字库没有的格子。
# 码位就是表里的码位：0xC0..0xDF/0xE0..0xFF 与 Latin-1 对齐，0x8C/0x9C 是表里用的
# SJIS 兼容码位，分别对应 Œ/œ。官中字库也没有这些码位，所以这 51 格在实机上是空的。
PAL_KEY_CODES = (
    0xC0, 0xC1, 0xC2, 0xC4, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE,
    0xCF, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD6, 0x8C, 0xD9, 0xDA, 0xDB, 0xDC,
    0xE0, 0xE1, 0xE2, 0xE4, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xEB, 0xEC, 0xED, 0xEE,
    0xEF, 0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF6, 0x9C, 0xF9, 0xFA, 0xFB, 0xFC, 0xDF,
)
PAL_KEY_CHAR = {0x8C: "\u0152", 0x9C: "\u0153"}

# 默认名字（主角/马）用的单字节码位：0xA1.. 依次对应下面这几个汉字。
#
# 背景：EU 版的名字输入路径（d_name_c::NameStrSet 的 PAL 分支）**每字符只取 1 字节**
# （`mChrInfo[i].mCharacter = static_cast<u8>(*moji); moji++;`），而且名字框是把这个字节
# 单独 `%c` 格式化进 J2DTextBox；官中的「林克」是 2 字节码位，被拆成两个假字后
# 还会把后面的 ESC(0x1B) 当前导字节的尾字节吞掉 → 名字框乱码。
#
# 但 0xA0..0xDF 在 ShiftJIS 里不是前导字节（JUTFont::isLeadByte_ShiftJIS 只看
# 0x81..0x9F / 0xE0..0xFC），所以字体路径（逐字节）与消息路径（parseCharacter_ShiftJIS）
# 都会把它当成**完整的单字节码位**，两边的码值还一致。于是把这些码位指到字库里
# 已有的汉字字形槽，就能不改引擎地让「林克 / 伊波娜」这种默认名正确显示。
# 副作用：一个字 = 1 个字符位置，名字长度上限 8 ⇒ 最多 8 个汉字。
NAME_DEFAULT_CHARS = "林克伊波娜"
NAME_DEFAULT_BASE = 0x00A1


class SlotPool:
    """键盘补全用的槽位池：先捡空闲槽，不够再用图集末尾的空 tail 槽。"""

    def __init__(self, free, tail):
        self.free = list(free)
        self.tail = list(tail)

    def take(self, what):
        if self.free:
            return self.free.pop(0)
        if self.tail:
            return self.tail.pop(0)
        sys.exit("键盘补全缺少可用槽位：%s" % what)


def pal_keyboard_aliases(orig_glyph, pool):
    """引擎标准键盘（ABC/abc 两页）里字库缺失的格子：分配槽位并待渲染。

    返回 (aliases, new_chars)：new_chars = {新槽: 字符}。
    """
    aliases = []
    new_chars = {}
    assigned = {}
    kept = added = 0
    for code in PAL_KEY_CODES:
        char = PAL_KEY_CHAR.get(code, chr(code))
        glyph = orig_glyph.get(ord(char))
        if glyph is not None:
            kept += 1
        else:
            glyph = assigned.get(char)
            if glyph is None:
                glyph = pool.take("标准键盘 %r" % char)
                assigned[char] = glyph
                new_chars[glyph] = char
            added += 1
        aliases.append((code, glyph))
    print("   标准键盘补全: %d 格 (原本就有 %d / 新增渲染 %d)" % (len(aliases), kept, added))
    return aliases, new_chars


def name_keyboard_aliases(orig_glyph, pool, open_mode=False):
    """引擎名字键盘字表（l_mojiZh）逐格别名。

    原字不在字库的：55 个日式写法换成对应简体字；其余格在 open 模式分配
    空槽/tail 槽用渲染字形补全，original 模式保持指向空白字形（U+3000）。
    返回 (aliases, new_chars, stats)：new_chars = {新槽: 字符}（待渲染）。
    """
    with open(NAME_KEYBOARD, encoding="utf-8") as f:
        doc = json.load(f)
    table = [int(c, 16) for c in doc["codes"]]
    blank = orig_glyph[0x3000]
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
                    glyph = pool.take("中文键盘 %r" % char)
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


def name_default_aliases(orig_glyph):
    """默认名字用的单字节码位（0xA1..）→ 字库里既有的字形槽。

    不新增槽位、不重渲染：只把码位指到已有字形，所以对像素与压缩结果零影响。
    返回 aliases = [(码位, 槽位)]。
    """
    aliases = []
    for i, char in enumerate(NAME_DEFAULT_CHARS):
        glyph = orig_glyph.get(ord(char))
        assert glyph is not None, "字库里没有默认名字的字形：%r" % char
        aliases.append((NAME_DEFAULT_BASE + i, glyph))
    print("   默认名单字节别名: %d 条 (%s -> %#x..%#x)"
          % (len(aliases), NAME_DEFAULT_CHARS, aliases[0][0], aliases[-1][0]))
    return aliases


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
            pool = SlotPool(free, tail)
            kb_aliases, new_chars, kb_stats = name_keyboard_aliases(
                orig_glyph, pool, open_mode=bool(renderer))
            pal_aliases, pal_chars = ((), {}) if not renderer else \
                pal_keyboard_aliases(orig_glyph, pool)
            new_chars.update(pal_chars)
            name_aliases = name_default_aliases(orig_glyph) if renderer else ()

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

            new_bfn = add_aliases(bytes(arc2), blocks, orig_glyph, remap,
                                  list(kb_aliases) + list(pal_aliases) + list(name_aliases))
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
                "pal": {
                    "aliases": [["%04X" % c, "%04X" % i] for c, i in pal_aliases],
                    "added": len(pal_chars),
                },
                "name_default": {
                    "aliases": [["%04X" % c, "%04X" % i] for c, i in name_aliases],
                    "chars": NAME_DEFAULT_CHARS,
                },
            }
    finally:
        if renderer:
            renderer.close()

    with open(KB_JSON, "w", encoding="utf-8") as f:
        json.dump(kb_tables, f, ensure_ascii=False, indent=1)
    print("wrote %s" % KB_JSON)


if __name__ == "__main__":
    main()
