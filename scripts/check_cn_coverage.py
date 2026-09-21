import glob
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bfn_repack as R

FONT = os.path.join(os.path.dirname(HERE), "cn", "font", "rodan_b_24_22.bfn")
TEXT = os.path.join(os.path.dirname(HERE), "cn", "text", "*.txt")


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

    counts = {}
    for p in sorted(glob.glob(TEXT)):
        for line in open(p, encoding="utf-8"):
            if line.startswith("#") or "\t" not in line:
                continue
            text = line.rstrip("\n").split("\t", 2)[2].replace("\\n", "\n")
            for ch in text:
                counts[ord(ch)] = counts.get(ord(ch), 0) + 1

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
