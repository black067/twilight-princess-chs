"""对照校验：把变体自己那份资源按引擎的方式解回字面串，与译文表逐条比。

比较前先折算打包时的两处有意改写：`<T060005>` → 字面 `※`，默认名单字节码位 `0xA1–0xA5` → 对应汉字。
"""

import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import codes
import material
import paths
import patch_sjis_font as PSF
import patch_sjis_text as PST
import text_resources as TR
import texts
import yaz0

NAME_BASE = PSF.NAME_DEFAULT_BASE
NAME_CHARS = PSF.name_default_chars()


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
    keys = TR.message_keys(resource, spec["mid1"])
    out = {}
    for k in range(n):
        off = struct.unpack_from(">I", blob, inf[0] + 0x10 + k * esize)[0]
        out[keys[k]] = engine_tokens(blob, dat_abs + off, dat_end, rev)
    return out


def pair_cells(blob, resource, shape, rev):
    """{key: token 列表}：单位表按引擎路径解（标签同正文一样编码，由 `%d %s` 拼进消息串）。"""
    secs = dict((t, (o, s)) for t, o, s in PST.sections(blob))
    inf, str1 = secs[b"INF1"], secs[b"STR1"]
    n, esize = struct.unpack_from(">HH", blob, inf[0] + 8)
    pool_abs, pool_end = str1[0] + 8, str1[0] + str1[1]
    out = {}
    for k in range(n):
        fields = struct.unpack_from(">" + "H" * (esize // 2), blob, inf[0] + 0x10 + k * esize)
        for name, field in shape["cells"].items():
            key = "%s/%d/%s" % (resource, k, name)
            out[key] = engine_tokens(blob, pool_abs + fields[field], pool_end, rev)
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


def reverse_map(space):
    """码位 -> 字面字符：own 查自分配码位表；sjis 只查搬过的那批。"""
    if space == paths.DEFAULT_CODE_SPACE:
        return {code: ch for ch, code in codes.load(paths.code_map_json()).items()}
    with open(paths.sjis_map_json(), encoding="utf-8") as f:
        remap = json.load(f)["remap"]
    return {int(new, 16): chr(int(old, 16)) for old, new in remap.items()}


def main():
    variant = paths.cli("--variant") or paths.OPEN_VARIANT
    if variant not in paths.VARIANT_NAMES:
        sys.exit("--variant 只支持 %s" % " / ".join(paths.VARIANT_NAMES))
    index, shapes = TR.load()
    # origin 的码位固定用 sjis 方案
    space = paths.code_space() if variant == paths.OPEN_VARIANT else "sjis"
    want = texts.read(texts.file(), texts.col_locale() if variant == paths.OPEN_VARIANT
                      else texts.col_draft())
    rev = reverse_map(space)
    parts = paths.parts_dir(variant, space)
    paths.check_manifest(parts, variant, space)
    print("变体 %s（%s 码位方案）：资源 %s，对照 %s" % (variant, space, parts, texts.file()))

    bad = []
    total = 0
    for base, spec in sorted(index.items()):
        path = os.path.join(parts, base)
        if not os.path.exists(path):
            sys.exit("缺资源 %s" % path)
        blobs = material.rarc_files(yaz0.decompress(open(path, "rb").read()))
        for f in spec["files"]:
            if "entries" not in f:
                continue
            resource = os.path.splitext(f["name"])[0]
            shape = shapes[resource]
            if shape["shape"] == "messages":
                cells = message_cells(blobs[f["name"]], f, resource, rev)
            else:
                cells = pair_cells(blobs[f["name"]], resource, shape, rev)
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
