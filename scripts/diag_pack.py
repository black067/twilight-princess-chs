"""验收判定：按引擎路径解码包内文本，查消息截断、缺字与名字键盘 550 格。

解码按引擎来：首字节不是前导（0x81–0x9F / 0xE0–0xFC）只吃 1 字节；`0` 结束消息，`0x1A` 后跟 1 字节 size。
"""

import collections
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bfn_repack as R
import paths
import yaz0


def is_lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC


def font_map(path):
    arc = yaz0.decompress(open(path, "rb").read())
    _, body, blocks = R.parse_bfn(arc)
    table = {}
    for magic, off, size in blocks:
        if magic != b"MAP1":
            continue
        method, sc, ec, n = struct.unpack_from(">HHHH", body, off + 8)
        if method == 3:
            for k in range(n):
                code, idx = struct.unpack_from(">HH", body, off + 0x10 + k * 4)
                table[code] = idx
        elif method == 0:
            for c in range(sc, ec + 1):
                table[c] = c
    return table


def sections(blob):
    pos = 0x20
    out = []
    while pos + 8 <= len(blob):
        tag = blob[pos : pos + 4]
        if not tag.isalnum():
            break
        size = struct.unpack_from(">I", blob, pos + 4)[0]
        out.append((tag, pos, size))
        pos += size
        while pos % 0x20:
            pos += 1
    return out


def walk_patched(blob, p, limit):
    """补丁后文本按引擎路径走：返回 (字符列表, 停止位置, 是否因码位 0 结束)"""
    chars = []
    while p + 1 < limit:
        at = p
        b = blob[p]
        if is_lead(b):
            code = (b << 8) | blob[p + 1]
            p += 2
        else:
            code = b
            p += 1
        if code == 0:
            return chars, at, True
        if code == 0x1A:
            if p >= limit:
                return chars, at, False
            size = blob[p]
            if size < 5:
                return chars, at, False
            p = at + size
            continue
        chars.append(code)
    return chars, p, False


def scan(path, fc):
    blob = yaz0.decompress(open(path, "rb").read())
    off = blob.find(b"MESG")
    if off < 0:
        return None
    inner = blob[off : off + struct.unpack_from(">I", blob, off + 8)[0]]
    S = sections(inner)
    tags = [s[0] for s in S]
    if b"INF1" not in tags or b"DAT1" not in tags:
        return {"empty": True}
    inf = next(s for s in S if s[0] == b"INF1")
    dat = next(s for s in S if s[0] == b"DAT1")
    nent, esize = struct.unpack_from(">HH", inner, inf[1] + 8)
    dat_abs = off + dat[1] + 8
    dat_end = off + dat[1] + dat[2]
    offs = sorted({struct.unpack_from(">I", inner, inf[1] + 0x10 + k * esize)[0] for k in range(nent)})
    bounds = offs[1:] + [dat_end - dat_abs]
    cut = 0
    missing = collections.Counter()
    chars_total = 0
    for old, bound in zip(offs, bounds):
        start = dat_abs + old
        lim = dat_abs + bound
        chars, stop, ended = walk_patched(blob, start, lim)
        chars_total += len(chars)
        for c in chars:
            if c < 0x20:
                continue
            if c not in fc:
                missing[c] += 1
        if not ended:
            cut += 1
    return {
        "msgs": len(offs),
        "cut": cut,
        "missing": missing,
        "chars": chars_total,
    }


def check_name_keyboard(path, fm, kb_path):
    """名字键盘 550 格逐格核对：
    1) 补丁字库里该码位的字形与 patch_sjis_font 落盘的期望表一致；
    2) 补全槽（新增渲染的格子）像素非空。
    """
    if not os.path.exists(kb_path):
        print("名字键盘: 缺 %s（先生成字库）" % kb_path)
        return
    with open(kb_path, encoding="utf-8") as f:
        doc = json.load(f)
    t = doc.get("fontres")
    assert t, "keyboard_aliases.json 缺 fontres 表"
    bad = []
    for code_s, idx_s in t["aliases"]:
        code, idx = int(code_s, 16), int(idx_s, 16)
        if fm.get(code) != idx:
            bad.append(code)
    print("名字键盘: %d 格 (原字 %d / 换简体 %d / 补全渲染 %d / 空白 %d), 不符 %d"
          % (len(t["aliases"]), t["direct"], t["variant"], t["added"], t["blanked"], len(bad)))
    if bad:
        print("   不符码位: %s" % " ".join("%04X" % c for c in bad[:20]))
    if not t["new_chars"]:
        return
    arc = yaz0.decompress(open(path, "rb").read())
    _, body, blocks = R.parse_bfn(arc)
    g = next(b for b in blocks if b[0] == b"GLY1")
    fields = R.gly1_fields(body, g[1])
    data = body[g[1] + 0x20 : g[1] + g[2]][: fields["textureSize"]]
    tw, rows = fields["textureWidth"], fields["numRows"]
    img = R.untile_i4(data, tw, fields["textureHeight"])
    empty = []
    for slot_s, ch in sorted(t["new_chars"].items()):
        slot = int(slot_s, 16)
        col, row = slot % rows, slot // rows
        ink = 0
        for y in range(fields["cellHeight"]):
            base = (row * fields["cellHeight"] + y) * tw + col * fields["cellWidth"]
            ink += sum(1 for v in img[base : base + fields["cellWidth"]] if v)
        if not ink:
            empty.append((slot, ch))
    print("   补全槽像素: %d 槽，空字形 %d %s"
          % (len(t["new_chars"]), len(empty), ["%#x:%s" % e for e in empty[:8]]))


def main():
    variant = paths.cli("--variant") or paths.OPEN_VARIANT
    if variant not in paths.PARTS_DIR:
        sys.exit("--variant 只支持 %s" % " / ".join(paths.PARTS_DIR))
    space = paths.code_space() if variant == paths.OPEN_VARIANT else "sjis"
    fontres_path = dict(paths.font_parts(variant))["fontres.arc"]
    fm = font_map(fontres_path)
    fc = set(fm)
    print("字库码位: %d（%s 变体 / %s 码位空间）" % (len(fc), variant, space))
    tot = collections.Counter()
    tot_missing = collections.Counter()
    msgs = 0
    for name, path in paths.text_parts(variant):
        r = scan(path, fc)
        if r is None or r.get("empty"):
            continue
        msgs += r["msgs"]
        tot["cut"] += r["cut"]
        tot["chars"] += r["chars"]
        tot_missing += r["missing"]
        print("%-22s msgs=%-5d 未正常结束=%-5d 缺字命中=%-4d"
              % (name, r["msgs"], r["cut"], sum(r["missing"].values())))
    print()
    print("合计：%d 条消息，%d 个字符，未正常结束 %d 条，缺字 %d 次" % (msgs, tot["chars"], tot["cut"], sum(tot_missing.values())))
    for c, n in tot_missing.most_common(20):
        print("   缺字码位 %04X x%-5d %s" % (c, n, chr(c) if 0x20 < c < 0xFFFF else "?"))
    print()
    if variant == paths.OPEN_VARIANT:
        check_name_keyboard(fontres_path, fm, paths.kb_json(space))
    else:
        print("名字键盘: 跳过（键盘补全只对 %s 变体成立）" % paths.OPEN_VARIANT)


main()
