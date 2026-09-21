import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import bfn_repack as R
import paths
import yaz0
from extract_entry import extract
from extract_index import HEADER_LEN, decrypt_region
from list_index import entries


def hexline(d, off, n):
    return " ".join("%02x" % d[off + i] for i in range(n))


def main():
    pak = paths.pak()
    with open(pak, "rb") as f:
        head = f.read(HEADER_LEN)
        size1 = struct.unpack_from("<I", head, 0x18)[0]
        index = decrypt_region(f, HEADER_LEN, size1, "header")
    recs = entries(index)
    data_start = HEADER_LEN + len(index)

    for name in ("res/Fontcn/fontres.arc", "res/Fontcn/rubyres.arc"):
        r = next(x for x in recs if x[0] == name)
        arc = yaz0.decompress(extract(pak, data_start, name, r[1], r[3]))
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
