import argparse
import os
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)

import bmg
import material
import paths
import yaz0


def bmg_entries(blob, off):
    size = struct.unpack_from(">I", blob, off + 8)[0]
    inner = blob[off : off + size]
    secs = bmg.sections(inner)
    inf = next(s for s in secs if s[0] == b"INF1")
    dat = next(s for s in secs if s[0] == b"DAT1")
    nent, esize = struct.unpack_from(">HH", inner, inf[1] + 8)
    dat_abs = off + dat[1] + 8
    dat_end = off + dat[1] + dat[2]
    out = []
    for k in range(nent):
        eo = inf[1] + 0x10 + k * esize
        o = struct.unpack_from(">I", inner, eo)[0]
        out.append((k, dat_abs + o, dat_end))
    return out


def read_string(blob, start, dat_end, limit=64):
    out = bytearray()
    i = start
    while i + 1 < dat_end:
        cu = (blob[i] << 8) | blob[i + 1]
        if cu == 0:
            break
        out += bytes(blob[i : i + 2])
        i += 2
        if len(out) >= limit * 2:
            break
    return bytes(out)


def show(tag, blob, off, ids):
    ents = bmg_entries(blob, off)
    print("== %s  entries=%d" % (tag, len(ents)))
    for k in ids:
        if k >= len(ents):
            continue
        _, start, dat_end = ents[k]
        s = read_string(blob, start, dat_end)
        codes = struct.unpack(">%dH" % (len(s) // 2), s) if len(s) % 2 == 0 else ()
        print("  id=%-5d bytes=%-4d raw=%s" % (k, len(s), s.hex()))
        print("            cps=%s" % " ".join("%04X" % c for c in codes))
        txt = "".join(chr(c) if 0x20 <= c < 0x7F or c > 0xA0 else "." for c in codes)
        print("            asciiish=%r" % txt[:64])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", help="地区（%s），决定默认成品包与包内消息目录"
                                    % " / ".join(paths.REGIONS))
    ap.add_argument("--variant", default=paths.OPEN_VARIANT,
                    choices=[v for v, _ in paths.VARIANTS])
    ap.add_argument("--dusk", help="成品包，默认取 config 的 out/<id>.dusk")
    ap.add_argument("--entry", help="包内条目，默认 overlay/res/<消息目录>/bmgres.arc")
    ap.add_argument("--ids", default="99,100,101,102,175")
    ap.add_argument("--cn-entry", default="bmgres.arc", help="源素材目录下的资源名，对照用")
    args = ap.parse_args()
    ids = [int(x) for x in args.ids.split(",")]
    region, language = paths.pick_disc(args.disc, "--disc")
    dusk = args.dusk or paths.package_path(args.variant, region, language)
    entry = args.entry or "overlay/res/%s/bmgres.arc" % paths.msg_dir(language)

    with zipfile.ZipFile(dusk) as z:
        names = z.namelist()
        raw = z.read(entry)
    print("dusk=%s names=%d" % (os.path.basename(dusk), len(names)))
    blob = yaz0.decompress(raw)
    off = blob.find(b"MESG")
    print("  yaz0ed=%d bytes, MESG@%#x" % (len(blob), off))
    show("PACK " + entry, blob, off, ids)

    arc = dict(material.msg_arcs())[args.cn_entry]
    off2 = arc.find(b"MESG")
    show("CN " + args.cn_entry, arc, off2, ids)


main()
