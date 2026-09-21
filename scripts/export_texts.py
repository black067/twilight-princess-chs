"""从 cn/msg/ 的归档导出 cn/texts.csv（一行 = BMG 里的一格文本）。

输入：cn/msg/*.arc.yaz0、data/msg_index.json、data/text_resources.json
输出：cn/texts.csv，列为 key,cn,zh-Hans,comment

  cn       导出的底稿快照，只读（打包取 zh-Hans）
  comment  写备注的列

形状（data/text_resources.json）：
  messages     消息表：单元 = 消息号，一格 = DAT1 正文
  string_pairs 短串表：单元 = 条目下标，格 = 条目里 u16 字段指到的 STR1 字符串
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import material
import patch_sjis_text as PST
import text_resources as TR
import texts

COL_DRAFT = "cn"
COL_COMMENT = "comment"
HEADER = (texts.COL_KEY, COL_DRAFT, texts.COL_LOCALE, COL_COMMENT)


def pool_codes(pool, at):
    """STR1 里的一个 2 字节串 -> 码位列表（码位 2 字节、`0000` 收尾）。"""
    codes = []
    i = at
    while i + 1 < len(pool):
        cu = (pool[i] << 8) | pool[i + 1]
        if cu == 0:
            break
        codes.append(cu)
        i += 2
    return codes


def file_cells(blob, resource, shape, spec):
    """{key: token 列表}：按形状读出这个文件里每一格的文本。"""
    if shape["shape"] == "messages":
        by_slot, pairs = PST.message_slots(blob)
        return {"%s/%d" % (resource, spec["mid1"][k]): by_slot[off] for k, off in pairs}

    secs = dict((t, (o, s)) for t, o, s in PST.sections(blob))
    inf, str1 = secs.get(b"INF1"), secs.get(b"STR1")
    if not inf or not str1 or shape.get("pool") != "STR1":
        sys.exit("%s 的形状与归档不符（string_pairs 需要 INF1 + STR1）" % resource)
    cnt, esize = struct.unpack_from(">HH", blob, inf[0] + 8)
    pool = blob[str1[0] + 8 : str1[0] + str1[1]]
    out = {}
    for k in range(cnt):
        fields = struct.unpack_from(">" + "H" * (esize // 2), blob, inf[0] + 0x10 + k * esize)
        for name, field in shape["cells"].items():
            key = "%s/%d/%s" % (resource, k, name)
            out[key] = [("chr", c) for c in pool_codes(pool, fields[field])]
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
        literal = literals[key]
        rows.append([key, literal, literal, ""])

    texts.write(texts.FILE, HEADER, rows)
    print("导出 %d 行 -> %s" % (len(rows), texts.FILE))
    print("  资源 %d 个：%s" % (len(shapes), " ".join(sorted(shapes))))


if __name__ == "__main__":
    main()
