"""从本地化方案的 source 目录导出原文表（校对底本）：只写字面原文，不碰译文表。

表路径 = langs.<lang>.src_file，缺省 <input_dir>/texts.<lang>.src.csv，**整表重写**。
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import material
import patch_sjis_text as PST
import paths
import text_resources as TR
import texts

COL_COMMENT = "comment"


def file_cells(blob, resource, shape, spec):
    """{key: token 列表}：按类型读出这个文件里每一条文本。"""
    encoding = PST.encoding_of(blob)
    if shape["shape"] == "messages":
        keys = TR.message_keys(resource, spec["mid1"])
        by_slot, pairs = PST.message_slots(blob)
        return {keys[k]: by_slot[off] for k, off in pairs}

    secs = dict((t, (o, s)) for t, o, s in PST.sections(blob))
    inf, str1 = secs.get(b"INF1"), secs.get(b"STR1")
    if not inf or not str1 or shape.get("pool") != "STR1":
        sys.exit("%s 的类型与归档不符（string_pairs 需要 INF1 + STR1）" % resource)
    cnt, esize = struct.unpack_from(">HH", blob, inf[0] + 8)
    pool = blob[str1[0] + 8 : str1[0] + str1[1]]
    out = {}
    for k in range(cnt):
        fields = struct.unpack_from(">" + "H" * (esize // 2), blob, inf[0] + 0x10 + k * esize)
        for name, field in shape["cells"].items():
            key = "%s/%d/%s" % (resource, k, name)
            out[key] = PST.pool_tokens(pool, fields[field], encoding)
    return out


def main():
    index, shapes = TR.load()
    sources = dict(material.msg_arcs())
    blobs = {}
    for base, arc in sources.items():
        for name, data in material.rarc_files(arc).items():
            blobs[(base, name)] = data

    literals = {}
    for base, spec in index.items():
        for f in spec["files"]:
            resource = os.path.splitext(f["name"])[0]
            shape = shapes[resource]
            for key, tokens in file_cells(blobs[(base, f["name"])], resource, shape, f).items():
                literal = texts.format_tokens(tokens)
                texts.check_roundtrip(tokens, literal, key)
                literals[key] = literal

    rows = []
    for base, f, resource, shape, key in TR.cells(index, shapes):
        rows.append([key, literals[key], ""])

    path = texts.src_file()
    texts.write(path, (texts.COL_KEY, texts.col_src(), COL_COMMENT), rows)
    print("导出原文 %d 行（%s）-> %s" % (len(rows), paths.lang(), path))
    print("  资源 %d 个：%s" % (len(shapes), " ".join(sorted(shapes))))


if __name__ == "__main__":
    main()
