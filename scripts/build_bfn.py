"""从零生成字库：BFN 与 RARC 自己写，只吃「码位表 + 键盘表 + 开源字体」。

字形槽 `0x00..0x5F` 留给 ASCII（`MAP1` method 0 恒等：槽 = 码位 − 0x20），其余按码位升序接在后面；
字宽表按字体前进宽度算。
"""

import json
import os
import struct
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bfn_repack as R
import codes
import font_render as font
import paths
import patch_sjis_font as PSF
import rarc
import yaz0

CODEMAP = paths.code_map_json()
OUT_DIR = paths.scratch_dir(paths.DEFAULT_CODE_SPACE)
KB_JSON = paths.kb_json(paths.DEFAULT_CODE_SPACE)

CELL = 48                      # 字形格边长（与原字库一致；引擎按格取纹理 UV）
ROWS = 64                      # 图集横向格数：纹理宽 = ROWS*CELL，高 = 列数*CELL
ASCII_LO, ASCII_HI = 0x20, 0x7F
BLANK_SLOT = ASCII_HI - ASCII_LO        # 0x7F（DEL，不渲染）= 通用空白槽
# (ascent, descent, width, leading)：与游戏排版对齐的度量，config 的 fonts.<name> 可覆盖。
# width 同时是全角前进宽度（引擎的 getWidth() / WID1 单位 = 格宽的 1/48）
DEFAULT_METRICS = {"fontres": (42, 6, 42, 48), "rubyres": (43, 5, 48, 48)}
# 部件名 -> 引擎按名字取的 BFN 名（mDoExt_initFont0/1 里写死）
FONTS = (("fontres", "rodan_b_24_22.bfn"), ("rubyres", "reishotai_24_22.bfn"))

# 引擎把半角 ASCII 转成全角码位时用的表（`JUTResFont::getFontCode` 里的同名字表）。
# 把这些码位也指到 ASCII 字形上，免得哪条路径先转过就查不到字形。
HALF_TO_FULL = (
    0x8140, 0x8149, 0x8168, 0x8194, 0x8190, 0x8193, 0x8195, 0x8166, 0x8169, 0x816A,
    0x8196, 0x817B, 0x8143, 0x817C, 0x8144, 0x815E, 0x824F, 0x8250, 0x8251, 0x8252,
    0x8253, 0x8254, 0x8255, 0x8256, 0x8257, 0x8258, 0x8146, 0x8147, 0x8183, 0x8181,
    0x8184, 0x8148, 0x8197, 0x8260, 0x8261, 0x8262, 0x8263, 0x8264, 0x8265, 0x8266,
    0x8267, 0x8268, 0x8269, 0x826A, 0x826B, 0x826C, 0x826D, 0x826E, 0x826F, 0x8270,
    0x8271, 0x8272, 0x8273, 0x8274, 0x8275, 0x8276, 0x8277, 0x8278, 0x8279, 0x816D,
    0x818F, 0x816E, 0x814F, 0x8151, 0x8165, 0x8281, 0x8282, 0x8283, 0x8284, 0x8285,
    0x8286, 0x8287, 0x8288, 0x8289, 0x828A, 0x828B, 0x828C, 0x828D, 0x828E, 0x828F,
    0x8290, 0x8291, 0x8292, 0x8293, 0x8294, 0x8295, 0x8296, 0x8297, 0x8298, 0x8299,
    0x829A, 0x816F, 0x8162, 0x8170, 0x8160,
)

CLI_TTF = paths.option("--ttf")
CLI_EM = paths.option("--em")


def keyboard_codes():
    """引擎名字键盘的 550 个码位。"""
    with open(os.path.join(paths.DATA, "name_keyboard.json"), encoding="utf-8") as f:
        return [int(c, 16) for c in json.load(f)["codes"]]


def sjis_char(code):
    return bytes((code >> 8, code & 0xFF)).decode("shift_jis")


def code_chars():
    """{码位: 字符}：译文码位 + 引擎固定码位；同一码位两种含义直接报错。"""
    pairs = {code: ch for ch, code in codes.load(CODEMAP).items()}
    fixed = {}
    for code, ch in PSF.ICON_ALIAS.items():
        fixed[code] = chr(ch)
    for code in keyboard_codes():
        fixed[code] = sjis_char(code)
    for code in PSF.PAL_KEY_CODES:
        fixed[code] = PSF.PAL_KEY_CHAR.get(code, chr(code))
    for i, ch in enumerate(PSF.name_default_chars()):
        fixed[PSF.NAME_DEFAULT_BASE + i] = ch
    clash = {c: (pairs[c], fixed[c]) for c in pairs.keys() & fixed.keys() if pairs[c] != fixed[c]}
    assert not clash, "码位冲突（译文码位被引擎固定码位占用）：%s" % clash
    pairs.update(fixed)
    return pairs


def halfwidth_aliases(slots):
    """[(全角码位, ASCII 槽)]：半角 ASCII 转成的全角码位也指到同一字形。"""
    out = []
    for i, code in enumerate(HALF_TO_FULL):
        ascii_code = ASCII_LO + i
        if ascii_code in slots:
            out.append((code, slots[ascii_code]))
    return out


def slots_of(pairs):
    """({码位: 字形槽}, 槽总数)：ASCII 走 method 0 恒等，其余按码位升序。"""
    slots = {c: c - ASCII_LO for c in range(ASCII_LO, ASCII_HI + 1)}
    nxt = ASCII_HI - ASCII_LO + 1
    for code in sorted(c for c in pairs if c not in slots):
        slots[code] = nxt
        nxt += 1
    return slots, nxt


def roster_of(slots, pairs):
    """{字形槽: 字符}。"""
    roster = {c - ASCII_LO: chr(c) for c in range(ASCII_LO, ASCII_HI + 1)}
    roster.update({slot: pairs[code] for code, slot in slots.items()
                   if not ASCII_LO <= code <= ASCII_HI})
    return roster


def geometry(total):
    """GLY1 字段：单页图集，槽数容得下 total。"""
    rows = ROWS
    cols = -(-total // rows)
    tw, th = rows * CELL, cols * CELL
    assert tw % 8 == 0 and th % 8 == 0, (tw, th)
    assert tw <= 16384 and th <= 16384, (tw, th)
    return {"startCode": 0, "endCode": total, "cellWidth": CELL, "cellHeight": CELL,
            "textureSize": tw * th // 2, "textureFormat": 0, "numRows": rows,
            "numColumns": cols, "textureWidth": tw, "textureHeight": th}


def ink_boxes(atlas, fields):
    """{槽: (x0, x1)}：图集里每格墨迹的横向范围，无墨迹的槽不出现。"""
    tw, cw, ch = fields["textureWidth"], fields["cellWidth"], fields["cellHeight"]
    rows = fields["numRows"]
    out = {}
    for slot in range(fields["startCode"], fields["endCode"]):
        col, row = slot % rows, slot // rows
        x0, x1 = cw, 0
        for y in range(ch):
            base = (row * ch + y) * tw + col * cw
            line = atlas[base : base + cw]
            if not any(line):
                continue
            for x in range(cw):
                if line[x]:
                    if x < x0:
                        x0 = x
                    if x + 1 > x1:
                        x1 = x + 1
        if x1 > x0:
            out[slot] = (x0, x1)
    return out


def wid_entries(roster, boxes, adv_em, total, full):
    """[(前导偏移, 前进宽度)]：每条对应一个字形槽。"""
    out = []
    for slot in range(total):
        ch = roster.get(slot)
        if ch is None:
            out.append((0, full))
            continue
        em_w = adv_em.get(ord(ch))
        if em_w is None:                            # 字体没有这个码位（控制字符）：按全/半角估
            em_w = 1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.5
        adv = max(1, int(round(em_w * full)))
        box = boxes.get(slot)
        out.append((max(0, (adv - (box[1] - box[0])) // 2) if box else 0, adv))
    return out


def block(tag, payload):
    """块 = magic + u32 总长 + payload；总长按 8 字节收尾（原字库也是这么排的）。"""
    size = (8 + len(payload) + 7) // 8 * 8
    return tag + struct.pack(">I", size) + payload + b"\x00" * (size - 8 - len(payload))


def build_bfn(slots, fields, atlas, metrics, wid):
    """拼 BFN：INF1 / GLY1 / MAP1(method 0) / MAP1(method 3) / WID1。"""
    ascent, descent, width, leading = metrics
    inf1 = block(b"INF1", struct.pack(">HHHHHH", 2, ascent, descent, width, leading, 0))

    tiled = R.tile_i4(atlas, fields["textureWidth"], fields["textureHeight"])
    assert len(tiled) == fields["textureSize"], (len(tiled), fields["textureSize"])
    gly1_head = struct.pack(">HHHHIHHHHH", fields["startCode"], fields["endCode"],
                            fields["cellWidth"], fields["cellHeight"], fields["textureSize"],
                            0, fields["numRows"], fields["numColumns"],
                            fields["textureWidth"], fields["textureHeight"])
    gly1 = block(b"GLY1", gly1_head + b"\x00\x00" + tiled)

    m0 = block(b"MAP1", struct.pack(">HHHH", 0, ASCII_LO, ASCII_HI, 0))
    entries = sorted((c, s) for c, s in slots.items() if not ASCII_LO <= c <= ASCII_HI)
    payload = struct.pack(">HHHH", 3, entries[0][0], entries[-1][0], len(entries))
    payload += b"".join(struct.pack(">HH", c, s) for c, s in entries)
    m3 = block(b"MAP1", payload)

    wid1 = block(b"WID1", struct.pack(">HH", 0, max(slots.values()))
                 + b"".join(struct.pack(">BB", lead, adv) for lead, adv in wid))

    blocks = inf1 + gly1 + m0 + m3 + wid1
    head = b"FONTbfn1" + struct.pack(">II", 0x20 + len(blocks), 5) + b"\x00" * 16
    return head + blocks


def engine_lookup(bfn, code):
    """按引擎 getFontCode 的取法求字形槽（method 0 恒等 + method 3 二分）。"""
    _, body, blocks = R.parse_bfn(bfn)
    for magic, off, size in blocks:
        if magic != b"MAP1":
            continue
        method, sc, ec, n = struct.unpack_from(">HHHH", body, off + 8)
        if not sc <= code <= ec:
            continue
        if method == 0:
            return code - sc
        if method == 3:
            pairs = [struct.unpack_from(">HH", body, off + 0x10 + k * 4) for k in range(n)]
            hit = [g for c, g in pairs if c == code]
            return hit[0] if hit else None
    return None


def self_check(arc, inner, slots, fields, wid, kb):
    """按引擎取法验归档与 BFN 结构（归档文件表 / 块表 / 查表 / 单页）。"""
    hdr = struct.unpack_from(">I", arc, 8)[0]
    nfiles = struct.unpack_from(">I", arc, hdr + 0x08)[0]
    file_off = hdr + struct.unpack_from(">I", arc, hdr + 0x0C)[0]
    stlen, stoff = struct.unpack_from(">II", arc, hdr + 0x10)
    st = arc[hdr + stoff : hdr + stoff + stlen]
    data = hdr + struct.unpack_from(">I", arc, 0x0C)[0]
    found = None
    for i in range(nfiles):
        o = file_off + i * 0x14
        fid, nh, tfno, doff, dsize = struct.unpack_from(">HHIII", arc, o)
        noff = tfno & 0xFFFFFF
        if noff >= len(st):
            continue
        nm = st[noff : st.index(b"\x00", noff)].decode()
        assert nh == rarc.name_hash(nm), "归档名字哈希不对：%s" % nm
        if nm == inner:
            found = arc[data + doff : data + doff + dsize]
    assert found is not None, "归档里取不到 %s" % inner

    assert found[:8] == b"FONTbfn1", "BFN 魔数不对：%r" % found[:8]
    assert struct.unpack_from(">I", found, 8)[0] == len(found), "BFN 头长度字段不对"
    assert struct.unpack_from(">I", found, 0xC)[0] == 5, "块数不是 5"
    _, body, blocks = R.parse_bfn(found)
    assert [b[0] for b in blocks] == [b"INF1", b"GLY1", b"MAP1", b"MAP1", b"WID1"], blocks
    assert body == found, "块表没铺满整个文件"

    g = next(b for b in blocks if b[0] == b"GLY1")
    gf = R.gly1_fields(found, g[1])
    for k, v in fields.items():
        assert gf[k] == v, "GLY1 字段 %s：%s != %s" % (k, gf[k], v)
    assert len(found) >= g[1] + g[2] and g[2] == 0x20 + gf["textureSize"], "GLY1 块长不对"
    pages = (gf["endCode"] - gf["startCode"] + gf["numRows"] * gf["numColumns"] - 1) \
        // (gf["numRows"] * gf["numColumns"])
    assert pages == 1, "不是单页：%d" % pages

    m0 = [b for b in blocks if b[0] == b"MAP1" and struct.unpack_from(">H", found, b[1] + 8)[0] == 0]
    assert len(m0) == 1 and struct.unpack_from(">H", found, m0[0][1] + 0x0A)[0] == ASCII_LO, \
        "method 0 段必须以 0x20 起（引擎按它的 startCode 决定要不要做半角转全角）"
    m3 = next(b for b in blocks if b[0] == b"MAP1" and struct.unpack_from(">H", found, b[1] + 8)[0] == 3)
    n = struct.unpack_from(">H", found, m3[1] + 0x0E)[0]
    pairs = [struct.unpack_from(">HH", found, m3[1] + 0x10 + k * 4) for k in range(n)]
    assert all(pairs[k][0] < pairs[k + 1][0] for k in range(n - 1)), "method 3 表没按码位升序"
    assert len(set(c for c, _ in pairs)) == n, "method 3 表有重复码位"
    assert not any(ASCII_LO <= c <= ASCII_HI for c, _ in pairs), "method 3 混进了 ASCII 段"
    assert len(pairs) == len(slots) - (ASCII_HI - ASCII_LO + 1), "method 3 条数与码位表不符"

    w = next(b for b in blocks if b[0] == b"WID1")
    wsc, wec = struct.unpack_from(">HH", found, w[1] + 8)
    assert (wsc, wec) == (0, max(slots.values())), "WID1 覆盖面不对"
    assert w[2] >= 0x0C + 2 * (wec - wsc + 1), "WID1 块长不够"

    for code, slot in slots.items():
        got = engine_lookup(found, code)
        assert got == slot, "码位 %#06x 查表得到 %s，应为 %s" % (code, got, slot)
    for code in kb:
        assert engine_lookup(found, code) == slots[code], "名字键盘码位 %#04x 查不到槽" % code
    return found


def main():
    if not os.path.exists(CODEMAP):
        sys.exit("缺 %s（先跑 build_bmg.py --code-space own，码位表要跟消息容器同一份）" % CODEMAP)
    pairs = code_chars()
    slots, total = slots_of(pairs)
    roster = roster_of(slots, pairs)
    kb = keyboard_codes()
    code_slots = dict(slots)
    code_slots.update(halfwidth_aliases(slots))      # 全角 ASCII 码位也指到 ASCII 字形
    cells = ROWS * (-(-total // ROWS))
    print("码位 %d 个（其中 ASCII %d、名字键盘 %d、全角 ASCII 别名 %d），字形槽 %d 个，图集 %d 格"
          % (len(code_slots), ASCII_HI - ASCII_LO + 1, len(kb),
             len(code_slots) - len(pairs), total, cells))
    assert total <= cells, (total, cells)

    os.makedirs(OUT_DIR, exist_ok=True)
    tables = {}
    for part, inner in FONTS:
        ttf, em, gamma = PSF.font_settings(part, CLI_TTF, CLI_EM)
        if not ttf or not os.path.exists(ttf):
            sys.exit("缺字体文件：config 的 fonts.%s.file（或 --ttf <路径>）" % part)
        cfg = (paths.lang_value("fonts") or {}).get(part) or {}
        ascent, descent, width, leading = DEFAULT_METRICS[part]
        ascent = int(cfg.get("ascent") or ascent)
        descent = int(cfg.get("descent") or descent)
        width = int(cfg.get("width") or width)
        leading = int(cfg.get("leading") or leading)

        cmap = font.parse_cmap(ttf)
        drawable = [(s, c) for s, c in sorted(roster.items())
                    if ord(c) >= 0x20 and ord(c) != 0x7F]
        missing = [(s, c) for s, c in drawable if ord(c) not in cmap]
        if missing:
            for slot, ch in missing[:20]:
                print("   缺字 槽 %#x 码位 U+%04X %r" % (slot, ord(ch), ch))
            sys.exit("字体缺 %d 个字符（不允许静默缺字）：%s" % (len(missing), ttf))

        fields = geometry(total)
        print("== %s（%s，em %.1f，gamma %.2f，ascent %d）"
              % (part, os.path.basename(ttf), em, gamma, ascent))
        with font.Renderer(ttf) as renderer:
            atlas, stats = font.render_atlas(renderer, roster, fields, em=em, gamma=gamma,
                                             baseline=ascent, anchor="baseline")
        print("   渲染 %d 字（按基线 %d 落位 / 裁剪 %d / 空 %d）"
              % (stats["rendered"], stats["fallback"], stats["clipped"], stats["blank"]))
        boxes = ink_boxes(atlas, fields)
        blank = [s for s, c in roster.items()
                 if s not in boxes and ord(c) > 0x20 and ord(c) != 0x7F and not c.isspace()]
        assert not blank, "这些字符渲染成空字形：%s" % [(hex(s), roster[s]) for s in blank[:10]]
        wid = wid_entries(roster, boxes, font.read_advances(ttf), total, width)
        bfn = build_bfn(code_slots, fields, atlas, (ascent, descent, width, leading), wid)

        w = rarc.Writer(part)
        w.add(inner, bfn)
        raw = w.build()
        self_check(raw, inner, code_slots, fields, wid, kb)
        path = os.path.join(OUT_DIR, part + ".arc")
        with open(path, "wb") as f:
            f.write(yaz0.encode(raw))
        print("   wrote %s (BFN %d 字节 -> 归档 %d 字节 -> yaz0 %d 字节)"
              % (path, len(bfn), len(raw), os.path.getsize(path)))
        if part == "fontres":
            tables[part] = {
                "aliases": [["%04X" % c, "%04X" % slots[c]] for c in kb],
                "new_chars": {"%04X" % slots[c]: sjis_char(c) for c in kb},
                "direct": 0, "variant": 0, "added": len(kb), "blanked": 0,
                "pal": {
                    "aliases": [["%04X" % c, "%04X" % slots[c]] for c in PSF.PAL_KEY_CODES],
                    "added": len(PSF.PAL_KEY_CODES),
                },
                "name_default": {
                    "aliases": [["%04X" % (PSF.NAME_DEFAULT_BASE + i),
                                 "%04X" % slots[PSF.NAME_DEFAULT_BASE + i]]
                                for i in range(len(PSF.name_default_chars()))],
                    "chars": PSF.name_default_chars(),
                },
            }
    with open(KB_JSON, "w", encoding="utf-8") as f:
        json.dump(tables, f, ensure_ascii=False, indent=1)
    print("wrote %s" % KB_JSON)
    print("下一步：把 %s/*.arc 拷进 %s 再打包（diag_pack.py 会核键盘每一格）"
          % (OUT_DIR, paths.parts_dir(paths.OPEN_VARIANT)))


main()
