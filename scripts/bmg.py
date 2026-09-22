import glob
import os
import struct
import sys


def sections(data, start=0x20):
    out = []
    pos = start
    while pos + 8 <= len(data):
        tag = data[pos : pos + 4]
        if not tag.isalnum():
            break
        size = struct.unpack_from(">I", data, pos + 4)[0]
        out.append((tag, pos, size))
        nxt = pos + size
        while nxt % 0x20:
            nxt += 1
        if nxt <= pos:
            break
        pos = nxt
    return out


def decode_attempts(raw):
    res = {}
    for enc in ("utf-16-be", "utf-8", "shift_jis", "cp936", "latin1"):
        try:
            res[enc] = raw.decode(enc)
        except Exception as e:
            res[enc] = "<%s>" % type(e).__name__
    return res


def main():
    pat = sys.argv[1] if len(sys.argv) > 1 else "input/msg/bmgres.arc"
    nmax = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    for p in sorted(glob.glob(pat)):
        data = open(p, "rb").read()
        pos = 0
        while True:
            i = data.find(b"MESG", pos)
            if i < 0:
                break
            pos = i + 4
            size = struct.unpack_from(">I", data, i + 8)[0]
            blob = data[i : i + size]
            style = blob[4:8]
            numsec = struct.unpack_from(">I", blob, 0x0C)[0]
            enc = struct.unpack_from(">I", blob, 0x10)[0]
            secs = sections(blob)
            print(
                "== %s @%#x  style=%s size=%d secs=%d enc=%d"
                % (os.path.basename(p), i, style.decode("latin1"), size, numsec, enc)
            )
            print("   sections: %s" % ", ".join("%s@%#x(%d)" % (t.decode("latin1"), o, s) for t, o, s in secs))
            inf = next((s for s in secs if s[0] == b"INF1"), None)
            dat = next((s for s in secs if s[0] == b"DAT1"), None)
            if not inf or not dat:
                print()
                continue
            nent, esize = struct.unpack_from(">HH", blob, inf[1] + 8)
            print("   INF1 entries=%d entrySize=%d" % (nent, esize))
            datdata = blob[dat[1] + 8 : dat[1] + dat[2]]
            for k in range(min(nmax, nent)):
                eo = inf[1] + 0x10 + k * esize
                off = struct.unpack_from(">I", blob, eo)[0]
                info = blob[eo + 4]
                tbt = blob[eo + 5]
                tbp = struct.unpack_from(">H", blob, eo + 6)[0]
                end = datdata.find(b"\x00", off)
                raw = datdata[off:end]
                print(
                    "   [%3d] off=%-6d info=%#04x tbt=%#04x tbp=%d len=%d" % (k, off, info, tbt, tbp, len(raw))
                )
                print("         hex : %s" % raw[:40].hex(" "))
                d = decode_attempts(raw)
                for e in ("utf-16-be", "utf-8", "cp936"):
                    print("         %-9s: %s" % (e, d[e][:60]))
            print()


if __name__ == "__main__":
    main()
