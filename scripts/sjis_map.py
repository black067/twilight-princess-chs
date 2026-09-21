import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import bfn_repack as R
import material
import paths

OUT = os.path.join(paths.WORK, "sjis_map.json")
NAME_KEYBOARD = os.path.join(paths.DATA, "name_keyboard.json")

NAME_KEYBOARD_REFMARK = 0x203B  # ※：文本里用来替掉 MSGTAG_REFMARK 插入的 1 字节 0x89


FULLWIDTH_ASCII_END = 0x829A
FIRST_LEAD = 0x89


def name_keyboard_codes():
    with open(NAME_KEYBOARD, encoding="utf-8") as f:
        return {int(c, 16) for c in json.load(f)["codes"]}


def safe_codes():
    leads = list(range(FIRST_LEAD, 0xA0)) + list(range(0xE0, 0xFD))
    trails = [t for t in range(0x40, 0xFD) if t != 0x7F]
    for lead in leads:
        for trail in trails:
            yield (lead << 8) | trail


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


def bmg_layout(blob, off):
    size = struct.unpack_from(">I", blob, off + 8)[0]
    inner = blob[off : off + size]
    secs = sections(inner)
    inf = next(s for s in secs if s[0] == b"INF1")
    dat = next(s for s in secs if s[0] == b"DAT1")
    nent, esize = struct.unpack_from(">HH", inner, inf[1] + 8)
    dat_abs = off + dat[1] + 8
    dat_end = off + dat[1] + dat[2]
    return inner, secs, inf, dat, nent, esize, dat_abs, dat_end


def decode_2byte(blob, start, dat_end):
    cps = []
    i = start
    blob_len = dat_end
    while i + 1 < dat_end:
        cu = (blob[i] << 8) | blob[i + 1]
        if cu == 0:
            break
        if cu == 0x001A:
            if i + 3 > blob_len:
                break
            u_size = blob[i + 2]
            if u_size < 6 or i + u_size > blob_len:
                break
            i += u_size
            continue
        cps.append(cu)
        i += 2
    return cps


def font_map1(bfn):
    start, body, blocks = R.parse_bfn(bfn)
    out = []
    for magic, off, size in blocks:
        if magic != b"MAP1":
            continue
        method, sc, ec, n = struct.unpack_from(">HHHH", body, off + 8)
        if method != 3:
            continue
        for k in range(n):
            code, idx = struct.unpack_from(">HH", body, off + 0x10 + k * 4)
            out.append((code, idx))
    return out


def main():
    arc = material.font_arcs()["fontres.arc"]
    start, body, blocks = R.parse_bfn(arc)
    entries_map = font_map1(body)
    print("font MAP1 method3 entries: %d" % len(entries_map))

    used = {}
    msgs = material.msg_arcs()
    print("msg archives: %d" % len(msgs))
    for base, blob in msgs:
        tail = base
        off = blob.find(b"MESG")
        if off < 0:
            print("  %-28s (no MESG, skipped)" % tail)
            continue
        try:
            inner, secs, inf, dat, nent, esize, dat_abs, dat_end = bmg_layout(blob, off)
        except StopIteration:
            print("  %-28s (no INF1/DAT1, skipped)" % tail)
            continue
        enc = inner[0x10]
        print("  %-28s entries=%-5d enc=%d sections=%s"
              % (tail, nent, enc, [s[0].decode() for s in secs]))
        for k in range(nent):
            eo = inf[1] + 0x10 + k * esize
            msg_off = struct.unpack_from(">I", inner, eo)[0]
            for cp in decode_2byte(blob, dat_abs + msg_off, dat_end):
                used[cp] = used.get(cp, 0) + 1

    print()
    print("distinct codepoints used: %d" % len(used))
    bad = {c: n for c, n in used.items() if c >= 0x20 and ((c >> 8) == 0 or (c & 0xFF) == 0)}
    print("codepoints containing a 0x00 byte: %d distinct / %d occurrences"
          % (len(bad), sum(bad.values())))

    font_codes = {c for c, _ in entries_map}
    missing = sorted(c for c in used if 0x80 <= c and c not in font_codes)
    buckets = {}
    for c in sorted(font_codes):
        buckets.setdefault(c >> 8, [0, 0])[0] += 1
    print("font MAP1 head-byte histogram (top 12): %s"
          % " ".join("%02x:%d" % (h, v[0]) for h, v in sorted(buckets.items())[:12]))
    print("used but absent from font MAP1: %d -> %s"
          % (len(missing), " ".join("%04X" % c for c in missing[:20])))

    universe = sorted({c for c, _ in entries_map} | {c for c in used if c >= 0x80})

    def legal_lead(b):
        return (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC)

    unsafe = [c for c in universe
              if c >= 0x80
              and ((c >> 8) == 0 or (c & 0xFF) == 0 or not legal_lead(c >> 8))
              and not (0x8140 <= c <= 0x833F)]

    # 名字键盘的码位必须空着（字库侧要给它们做别名）。与正文“保留”码位撞车的，
    # 把正文那个码位也重映射走，腾出位子。
    names = name_keyboard_codes()
    kept_before = set(universe) - set(unsafe)
    forced = {NAME_KEYBOARD_REFMARK} | (names & kept_before)
    unsafe = sorted(set(unsafe) | (forced & set(universe)))
    kept = [c for c in universe if c not in set(unsafe)]
    print("codes in play: %d; need remap: %d; kept as-is: %d (names share %d with kept)"
          % (len(universe), len(unsafe), len(kept), len(names & kept_before)))
    gen = safe_codes()
    avoid = set(kept) | names
    remap = {}
    for code in unsafe:
        new = next(gen)
        while new in avoid or new <= FULLWIDTH_ASCII_END:
            new = next(gen)
        remap[code] = new
    print("new code range: %#x..%#x (avoids kept codes and engine-synthesised targets)"
          % (remap[unsafe[0]], remap[unsafe[-1]]))
    print("kept range: %#x..%#x" % (kept[0], kept[-1]))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "remap": {"%04X" % k: "%04X" % v for k, v in remap.items()},
            "font_entries": [["%04X" % c, "%04X" % i] for c, i in entries_map],
            "new_range": ["%04X" % remap[unsafe[0]], "%04X" % remap[unsafe[-1]]],
            "kept_range": ["%04X" % kept[0], "%04X" % kept[-1]],
        }, f, indent=1)

    print("wrote %s" % OUT)


main()
