"""文本资源的 key：`<资源>/<条目号>[/<字段名>]` 的枚举与拆解。"""

import json
import os
import sys

import paths

SHAPES_JSON = os.path.join(paths.DATA, "text_resources.json")


def load():
    """(索引表, 类型表)。"""
    with open(paths.msg_index_json(), encoding="utf-8") as f:
        index = json.load(f)
    with open(SHAPES_JSON, encoding="utf-8") as f:
        shapes = json.load(f)["resources"]
    return index, shapes


def parse(key):
    """`<资源>/<条目号>[/<字段名>]` -> (资源, 条目号, 字段名)。"""
    parts = key.split("/")
    if len(parts) == 2:
        return parts[0], parts[1], None
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    sys.exit("key 写法不对（应为 <资源>/<条目号> 或 <资源>/<条目号>/<字段名>）：%r" % key)


def message_keys(resource, mid1):
    """消息表的 key：`<资源>/<消息号>`，消息号重复时补 `#<下标>`。

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
    """[(归档, 文件表项, 资源, 类型, key)]：按归档、文件、条目号、类型表里的顺序排。"""
    out = []
    for base, spec in sorted(index.items()):
        for f in spec["files"]:
            resource = os.path.splitext(f["name"])[0]
            shape = shapes.get(resource)
            if shape is None:
                sys.exit("data/text_resources.json 里没有 %r 的类型" % resource)
            if shape["shape"] == "messages":
                for key in message_keys(resource, f["mid1"]):
                    out.append((base, f, resource, shape, key))
            elif shape["shape"] == "string_pairs":
                for k in range(f["entries"]):
                    for name in shape["cells"]:
                        out.append((base, f, resource, shape, "%s/%d/%s" % (resource, k, name)))
            else:
                sys.exit("不认识的类型 %r（%s）" % (shape["shape"], resource))
    return out
