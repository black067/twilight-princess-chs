"""从 lang 的源素材现算容器索引表：data/msg_index.<lang>.json。

必须与源素材同源：换语言（--lang）或换素材后重跑一次。
"""

import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import material
import paths
import patch_sjis_text as PST

MAGIC = b"MESG"
HEAD = 0x20
ATTR_FIELDS = (b"INF1", b"DAT1", b"MID1", b"STR1")


def runs(values):
    """[值] -> (去重值列表, 每段的重复次数)。"""
    pool, runs_out = [], []
    for value in values:
        if value not in pool:
            pool.append(value)
        idx = pool.index(value)
        if runs_out and runs_out[-1][0] == idx:
            runs_out[-1][1] += 1
        else:
            runs_out.append([idx, 1])
    return pool, [x for pair in runs_out for x in pair]


def dump(node, level=0):
    """与 `json.dumps(indent=1)` 同形，但数字数组保持单行（mid1 有 5000 项，逐行没法看）。"""
    if isinstance(node, dict):
        if not node:
            return "{}"
        pad = " " * (level + 1)
        items = [pad + json.dumps(k, ensure_ascii=False) + ": " + dump(v, level + 1)
                 for k, v in node.items()]
        return "{\n" + ",\n".join(items) + "\n" + " " * level + "}"
    if isinstance(node, list):
        if all(not isinstance(x, (dict, list)) for x in node):
            return "[" + ", ".join(json.dumps(x, ensure_ascii=False) for x in node) + "]"
        pad = " " * (level + 1)
        items = [pad + dump(x, level + 1) for x in node]
        return "[\n" + ",\n".join(items) + "\n" + " " * level + "]"
    return json.dumps(node, ensure_ascii=False)


def file_spec(name, blob):
    off = blob.find(MAGIC)
    if off < 0:
        return None
    secs = PST.sections(blob)
    body = [s for s in secs if s[0] in ATTR_FIELDS]
    tails = [{"tag": s[0].decode(), "size": s[2]} for s in secs if s[0] not in ATTR_FIELDS]
    inf = next(s for s in secs if s[0] == b"INF1")
    entries, esize = struct.unpack_from(">HH", blob, inf[1] + 8)
    attrs = [blob[inf[1] + 0x10 + k * esize + 6: inf[1] + 0x10 + (k + 1) * esize]
             for k in range(entries)]
    pool, attr_runs = runs(attrs)

    mid = next((s for s in secs if s[0] == b"MID1"), None)
    str1 = next((s for s in secs if s[0] == b"STR1"), None)
    count = struct.unpack_from(">H", blob, mid[1] + 8)[0] if mid else 0
    mid1 = list(struct.unpack_from(">%dI" % count, blob, mid[1] + 0x10)) if mid else []
    assert count in (0, entries), (name, count, entries)

    return {
        "name": name,
        "entries": entries,
        "entrySize": esize,
        "encoding": blob[off + 0x10],
        "mid1": mid1,
        "attrs": [a.hex() for a in pool] if mid else [],
        "attrRuns": attr_runs if mid else [],
        "str1Size": str1[2] if str1 else 0,
        "bmgSize": HEAD + sum(s[2] for s in body),
        "fileSize": len(blob),
        "tails": tails,
    }


def main():
    index = {}
    for base, arc in material.msg_arcs():
        files = []
        for name, blob in sorted(material.rarc_files(arc).items()):
            spec = file_spec(name, blob)
            if spec:
                files.append(spec)
        index[base] = {"files": files}

    path = paths.msg_index_json()
    with open(path, "w", encoding="utf-8") as f:
        f.write(dump(index))
        f.write("\n")
    total = sum(len(s["files"]) for s in index.values())
    print("索引 %d 个归档 / %d 个文件 -> %s（%s）" % (len(index), total, path, paths.lang()))


if __name__ == "__main__":
    main()
