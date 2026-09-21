"""验收判定：按引擎 ShiftJIS 路径解码包内文本，检查
  1) 消息是否会在中途被判为结束（对白切断）
  2) 画出来的码位是否都在补丁字库里（缺字）
  3) 名字键盘（l_mojiZh）的 550 个码位是否都在字库里，且指向预期的字形

引擎路径（源码）：
  parseCharacter_ShiftJIS: 首字节不是前导(0x81-0x9F/0xE0-0xFC) => 只吃 1 字节
  process_character_: iCharacter==0 => 消息结束；==0x1A => tag；否则字符
  on_tag_: 下一元素 = marker + size（marker 1 字节），tag 处理器拿到 size-5 字节
"""

import collections
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bfn_repack as R
import patch_sjis_font as F
import paths
import yaz0

PARTS = os.path.join(paths.WORK, "sjis_parts")


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


def check_name_keyboard(orig, fm):
    """550 个键盘格子逐格核：补丁字库里该码位的字形与预期一致

    预期按原始字库码表算——重映射后的码位会与别的字符的 Unicode 值撞车，
    不能用补丁字库反查。
    """
    with open(F.NAME_KEYBOARD, encoding="utf-8") as f:
        codes = [int(c, 16) for c in json.load(f)["codes"]]
    blank = orig[0x3000]
    direct = variant = blanked = 0
    bad = []
    for code in codes:
        char = bytes((code >> 8, code & 0xFF)).decode("shift_jis")
        want = orig.get(ord(char))
        if want is not None:
            direct += 1
        else:
            target = F.NAME_VARIANT.get(char)
            want = orig.get(ord(target)) if target else None
            if want is not None:
                variant += 1
            else:
                want = blank
                blanked += 1
        if fm.get(code) != want:
            bad.append(code)
    print("名字键盘: %d 格 (原字 %d / 换简体 %d / 空白 %d), 不符 %d"
          % (len(codes), direct, variant, blanked, len(bad)))
    if bad:
        print("   不符码位: %s" % " ".join("%04X" % c for c in bad[:20]))


def main():
    with open(os.path.join(paths.WORK, "sjis_map.json"), encoding="utf-8") as f:
        orig = {int(c, 16): int(i, 16) for c, i in json.load(f)["font_entries"]}
    fm = font_map(os.path.join(PARTS, "res_Fonteu_fontres.arc"))
    fc = set(fm)
    print("字库码位: %d" % len(fc))
    tot = collections.Counter()
    tot_missing = collections.Counter()
    msgs = 0
    for n in sorted(x for x in os.listdir(PARTS) if x.startswith("res_Msgfr_")):
        r = scan(os.path.join(PARTS, n), fc)
        if r is None or r.get("empty"):
            continue
        msgs += r["msgs"]
        tot["cut"] += r["cut"]
        tot["chars"] += r["chars"]
        tot_missing += r["missing"]
        print("%-22s msgs=%-5d 未正常结束=%-5d 缺字命中=%-4d" % (n, r["msgs"], r["cut"], sum(r["missing"].values())))
    print()
    print("合计：%d 条消息，%d 个字符，未正常结束 %d 条，缺字 %d 次" % (msgs, tot["chars"], tot["cut"], sum(tot_missing.values())))
    for c, n in tot_missing.most_common(20):
        print("   缺字码位 %04X x%-5d %s" % (c, n, chr(c) if 0x20 < c < 0xFFFF else "?"))
    print()
    check_name_keyboard(orig, fm)


main()
