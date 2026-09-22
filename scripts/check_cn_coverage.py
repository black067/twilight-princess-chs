"""看译文用到哪些字符、原字库能不能渲染：判断保留原字库位图的变体能不能画全。

只统计就地改写路线会重建的格（`messages` 形状的消息表）；短串表是原样带过的，不算在内。
"""

import csv
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bfn_repack as R
import paths
import text_resources as TR
import texts

FONT = os.path.join(paths.font_source_dir(), "rodan_b_24_22.bfn")


def load_maps(bfn):
    _, body, blocks = R.parse_bfn(bfn)
    maps = []
    for magic, off, size in blocks:
        if magic != b"MAP1":
            continue
        method, start, end, entries = struct.unpack_from(">HHHH", body, off + 8)
        maps.append({"method": method, "start": start, "end": end, "entries": entries,
                     "data": body[off + 0x10 : off + size]})
    return maps


def renderable(code, maps):
    for m in maps:
        if not (m["start"] <= code <= m["end"]):
            continue
        if m["method"] == 0:
            return True
        if m["method"] == 3:
            n = m["entries"]
            lo, hi = 0, n - 1
            data = m["data"]
            while lo <= hi:
                mid = (lo + hi) // 2
                full = struct.unpack_from(">H", data, mid * 4)[0]
                if code < full:
                    hi = mid - 1
                elif code > full:
                    lo = mid + 1
                else:
                    return True
            return False
    return False


def main():
    bfn = open(FONT, "rb").read()
    maps = load_maps(bfn)
    for m in maps:
        print("MAP1 method=%d start=%#x end=%#x entries=%d" % (m["method"], m["start"], m["end"], m["entries"]))

    index, shapes = TR.load()
    messages = {key for _, _, _, shape, key in TR.cells(index, shapes) if shape["shape"] == "messages"}
    counts = {}
    with open(texts.file(), encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for rec in reader:
            if rec[texts.COL_KEY] not in messages:
                continue
            for tok in texts.parse_literal(rec[texts.col_locale()]):
                if tok[0] == "chr":
                    counts[tok[1]] = counts.get(tok[1], 0) + 1

    total = sum(counts.values())
    distinct = len(counts)
    missing = {c: n for c, n in counts.items() if not renderable(c, maps)}
    missing_chars = sum(missing.values())
    print()
    print("字符总出现次数 %d，去重码位 %d" % (total, distinct))
    print("字库覆盖不到：%d 个码位 / %d 次出现" % (len(missing), missing_chars))
    ctrl = {c: n for c, n in missing.items() if c < 0x20}
    other = {c: n for c, n in missing.items() if c >= 0x20}
    print("  其中 <0x20 控制码：%d 个码位 / %d 次" % (len(ctrl), sum(ctrl.values())))
    print("  其它：%d 个码位 / %d 次" % (len(other), sum(other.values())))
    top = sorted(other.items(), key=lambda kv: -kv[1])[:25]
    print("  出现最多的其它码位：" + " ".join("U+%04X×%d" % (c, n) for c, n in top))


if __name__ == "__main__":
    main()
