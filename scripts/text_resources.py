"""文本资源的格：`<资源>/<单元>[/<格名>]` 的枚举与拆解。

形状表在 data/text_resources.json，条数与消息号在当前语言的 data/msg_index.<lang>.json。
"""

import json
import os
import sys

import paths

SHAPES_JSON = os.path.join(paths.DATA, "text_resources.json")


def load():
    """(索引表, 形状表)。"""
    with open(paths.msg_index_json(), encoding="utf-8") as f:
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


def message_keys(resource, mid1):
    """消息表的格键：`<资源>/<消息号>`，消息号重复时补 `#<下标>`。

    原归档里出现过同一消息号两条（后一条引擎查不到，文本可能为空），键必须能区分它们。
    """
    seen = {}
    out = []
    for k, mid in enumerate(mid1):
        n = seen.get(mid, 0)
        seen[mid] = n + 1
        out.append("%s/%d%s" % (resource, mid, "" if n == 0 else "#%d" % k))
    return out


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
                for key in message_keys(resource, f["mid1"]):
                    out.append((base, f, resource, shape, key))
            elif shape["shape"] == "string_pairs":
                for k in range(f["entries"]):
                    for name in shape["cells"]:
                        out.append((base, f, resource, shape, "%s/%d/%s" % (resource, k, name)))
            else:
                sys.exit("不认识的形状 %r（%s）" % (shape["shape"], resource))
    return out
