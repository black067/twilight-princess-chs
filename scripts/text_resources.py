"""文本资源的格：`<资源>/<单元>[/<格名>]` 的枚举与拆解。

形状表在 data/text_resources.json，条数与消息号在 data/msg_index.json。
"""

import json
import os
import sys

import paths

INDEX_JSON = os.path.join(paths.DATA, "msg_index.json")
SHAPES_JSON = os.path.join(paths.DATA, "text_resources.json")


def load():
    """(索引表, 形状表)。"""
    with open(INDEX_JSON, encoding="utf-8") as f:
        index = json.load(f)
    with open(SHAPES_JSON, encoding="utf-8") as f:
        shapes = json.load(f)["resources"]
    return index, shapes


def parse(key):
    """`<资源>/<单元>[/<格名>]` -> (资源, 单元, 格名)。"""
    parts = key.split("/")
    if len(parts) == 2:
        return parts[0], parts[1], None
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    sys.exit("key 写法不对（应为 <资源>/<单元> 或 <资源>/<单元>/<格名>）：%r" % key)


def cells(index, shapes):
    """[(归档, 文件表项, 资源, 形状, key)]：按归档、文件、单元、形状表里的格顺序排。"""
    out = []
    for base, spec in sorted(index.items()):
        for f in spec["files"]:
            resource = os.path.splitext(f["name"])[0]
            shape = shapes.get(resource)
            if shape is None:
                sys.exit("data/text_resources.json 里没有 %r 的形状" % resource)
            if shape["shape"] == "messages":
                for mid in f["mid1"]:
                    out.append((base, f, resource, shape, "%s/%d" % (resource, mid)))
            elif shape["shape"] == "string_pairs":
                for k in range(f["entries"]):
                    for name in shape["cells"]:
                        out.append((base, f, resource, shape, "%s/%d/%s" % (resource, k, name)))
            else:
                sys.exit("不认识的形状 %r（%s）" % (shape["shape"], resource))
    return out
