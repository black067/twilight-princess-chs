"""对照校验：把 work/sjis_parts 的部件按引擎口径解回字面串，与 cn/texts.csv 逐格比。

引擎路径：非前导字节吃 1 字节、前导字节（0x81–0x9F / 0xE0–0xFC）吃 2 字节、
`0x1A` 后跟 1 字节长度是标签。打包时有两处有意改写，比较前统一：

  `<T060005>`（装饰性 ※ 标签） -> 字面 `※`
  默认名的单字节码位（0xA1–0xA5） -> 表里对应的汉字
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import codes
import export_texts as ET
import material
import patch_sjis_font as PSF
import patch_sjis_text as PST
import text_resources as TR
import texts
import yaz0

NAME_BASE = PSF.NAME_DEFAULT_BASE
NAME_CHARS = PSF.NAME_DEFAULT_CHARS


def is_lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC


def engine_tokens(blob, p, limit, rev):
    """按引擎路径解一条消息 -> token 列表。"""
    out = []
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
            break
        if code == 0x1A:
            size = blob[p]
            out.append(("tag", bytes(blob[at + 2 : at + 5]), bytes(blob[at + 5 : at + size])))
            p = at + size
            continue
        out.append(("chr", ord(rev[code]) if code in rev else code))
    return out


def message_cells(blob, spec, resource, rev):
    """{key: token 列表}：消息表按引擎路径解。"""
    secs = dict((t, (o, s)) for t, o, s in PST.sections(blob))
    inf, dat = secs[b"INF1"], secs[b"DAT1"]
    n, esize = struct.unpack_from(">HH", blob, inf[0] + 8)
    dat_abs, dat_end = dat[0] + 8, dat[0] + dat[1]
    out = {}
    for k in range(n):
        off = struct.unpack_from(">I", blob, inf[0] + 0x10 + k * esize)[0]
        out["%s/%d" % (resource, spec["mid1"][k])] = engine_tokens(blob, dat_abs + off, dat_end, rev)
    return out


def normalize(tokens):
    """把打包时的有意改写折算回 CSV 的写法。"""
    out = []
    for tok in tokens:
        if tok[0] == "tag" and int.from_bytes(tok[1], "big") == PST.REFMARK_TAG:
            out.append(("chr", PST.REFMARK_CHAR))
        elif tok[0] == "chr" and NAME_CHARS and NAME_BASE <= tok[1] < NAME_BASE + len(NAME_CHARS):
            out.append(("chr", ord(NAME_CHARS[tok[1] - NAME_BASE])))
        else:
            out.append(tok)
    return out


def main():
    index, shapes = TR.load()
    want = texts.read(texts.FILE)
    rev = {code: ch for ch, code in codes.load(os.path.join(ROOT, "work", "code_map.json")).items()}
    parts = os.path.join(ROOT, "work", "sjis_parts")

    bad = []
    total = 0
    for base, spec in sorted(index.items()):
        path = os.path.join(parts, base)
        if not os.path.exists(path):
            sys.exit("缺部件 %s" % path)
        blobs = material.rarc_files(yaz0.decompress(open(path, "rb").read()))
        for f in spec["files"]:
            if "entries" not in f:
                continue
            resource = os.path.splitext(f["name"])[0]
            shape = shapes[resource]
            if shape["shape"] == "messages":
                cells = message_cells(blobs[f["name"]], f, resource, rev)
            else:
                cells = ET.file_cells(blobs[f["name"]], resource, shape, f)
            for key, tokens in cells.items():
                total += 1
                got = texts.format_tokens(normalize(tokens))
                expect = texts.format_tokens(normalize(texts.parse_literal(want[key])))
                if got != expect:
                    bad.append((key, got, expect))
    for key, got, expect in bad[:5]:
        print("不一致 %s\n  包内 %s\n  CSV  %s" % (key, ascii(got), ascii(expect)))
    print("比对 %d 格，不一致 %d 格" % (total, len(bad)))


if __name__ == "__main__":
    main()
