"""texts.csv 的读写：一行 = BMG 里的一格文本。

本模块只认 `key` 与两个文本列：译文列 `zh-Hans`、原文列 `cn`。其余列不参与打包。

    key,zh-Hans
    zel_00/1,译文
    zel_unit/0/one,支箭

`key` = `<资源>/<单元>[/<格名>]`：资源名是 BMG 文件名去掉 `.bmg`；消息的单元是消息号，
其它表的单元是条目下标；格名只在多格资源上出现（`zel_unit` 的 `one` / `other`）。

文本字面语法（一格文本 ↔ 一个字符串）
    普通字符         原样
    换行（U+000A）   `\\n`
    其它控制码       `\\xNN`
    标签             `<Tggcccc>`（gg = 高字节，cccc = 低 16 位）
    带数据的标签     `<Tggcccc:hex>`（hex = payload 字节）

文本里真的带反斜杠或形如 `<T……>` 的片段时，字面串读不回同一串 token，导出会报错。
"""

import csv
import os
import re

import paths

FILE = os.path.join(paths.CN, "texts.csv")
COL_KEY = "key"
COL_LOCALE = "zh-Hans"     # 译文列
COL_SOURCE = "cn"          # 原文列

TAG_RE = re.compile(r"<T([0-9a-f]{6})(?::([0-9a-f]*))?>")


def format_tokens(tokens):
    """token 列表 -> 字面串。"""
    out = []
    for token in tokens:
        if token[0] == "tag":
            tag = int.from_bytes(token[1], "big")
            out.append("<T%06x" % tag)
            if token[2]:
                out.append(":%s" % token[2].hex())
            out.append(">")
            continue
        code = token[1]
        if code == 0x0A:
            out.append("\\n")
        elif code < 0x20 or code == 0x7F:
            out.append("\\x%02x" % code)
        else:
            out.append(chr(code))
    return "".join(out)


def check_roundtrip(tokens, literal, where):
    """字面串必须能读回同一串 token。"""
    if parse_literal(literal) != list(tokens):
        raise SystemExit("%s 的文本写不成字面串：%r" % (where, literal))


def parse_literal(literal):
    """字面串 -> token 列表（与 patch_sjis_text.decode 同形）。"""
    out = []
    i = 0
    while i < len(literal):
        rest = literal[i:]
        if rest.startswith("<T"):
            m = TAG_RE.match(rest)
            if not m:
                raise SystemExit("标签写法不对（应为 <Tggcccc> 或 <Tggcccc:hex>）：%r" % rest[:16])
            payload = bytes.fromhex(m.group(2)) if m.group(2) else b""
            out.append(("tag", int(m.group(1), 16).to_bytes(3, "big"), payload))
            i += m.end()
            continue
        if rest.startswith("\\n"):
            out.append(("chr", 0x0A))
            i += 2
            continue
        if rest.startswith("\\x") and len(rest) >= 4:
            out.append(("chr", int(rest[2:4], 16)))
            i += 4
            continue
        if rest[0] == "\\":
            raise SystemExit("控制码写法不对（应为 \\n 或 \\xNN）：%r" % rest[:8])
        out.append(("chr", ord(rest[0])))
        i += 1
    return out


def read(path=FILE, locale=COL_LOCALE):
    """读 CSV -> {key: 字面串}。表头缺列、key 重复、行与表头列数不符都直接报错。"""
    if not os.path.exists(path):
        raise SystemExit("缺 %s（用 export_texts.py 从素材导出）" % path)
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise SystemExit("%s 是空文件" % path)
        for col in (COL_KEY, locale):
            if col not in header:
                raise SystemExit("%s 的表头缺 %r 列：%s" % (path, col, header))
        rows = {}
        for line_no, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise SystemExit("%s 第 %d 行列数与表头不符（%d != %d）"
                                 % (path, line_no, len(row), len(header)))
            rec = dict(zip(header, row))
            key = rec[COL_KEY].strip()
            if not key:
                raise SystemExit("%s 第 %d 行 key 为空" % (path, line_no))
            if key in rows:
                raise SystemExit("%s 第 %d 行 key 重复：%s" % (path, line_no, key))
            rows[key] = rec[locale]
    return rows


def write(path, header, rows):
    """写 CSV：UTF-8 带 BOM、LF、字段按需加引号。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
