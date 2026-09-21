import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import bfn_repack as R
import material


def hexline(d, off, n):
    return " ".join("%02x" % d[off + i] for i in range(n))


def main():
    arcs = material.font_arcs()
    for name in ("fontres.arc", "rubyres.arc"):
        arc = arcs[name]
        start, bfn, blocks = R.parse_bfn(arc)
        print("== %s  arc=%d  bfn@%#x size=%d" % (name, len(arc), start, len(bfn)))
        print("   header: %s" % hexline(bfn, 0, 0x20))
        for magic, off, size in blocks:
            print("   %s off=%#x size=%d" % (magic.decode(), off, size))
            if magic == b"INF1":
                print("      %s" % hexline(bfn, off, min(size, 0x18)))
            if magic == b"MAP1":
                n = struct.unpack_from(">H", bfn, off + 0xE)[0]
                print("      method=%d start=%#x end=%#x entries=%d"
                      % (struct.unpack_from(">H", bfn, off + 8)[0],
                         struct.unpack_from(">H", bfn, off + 0xA)[0],
                         struct.unpack_from(">H", bfn, off + 0xC)[0], n))
                print("      head: %s" % hexline(bfn, off + 0x10, 16))
                print("      tail: %s" % hexline(bfn, off + size - 16, 16))
        print()


main()
