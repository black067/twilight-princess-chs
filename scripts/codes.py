"""码位分配：给译文用到的字符分配新码位，不依赖原字库的码位表。

引擎对码位的三条要求（`patch_sjis_font.py` 的「修法」与 `docs/技术备忘.md`）：
  1. 首字节是合法前导：0x81–0x9F / 0xE0–0xFC（`isLeadByte_ShiftJIS`）
  2. 码位 ≥ 0x8800，否则被 `change1ByteTo2Bytes` / `changeKataToHira` 改写
  3. 两字节都不为 0x00（0x00 会被 `process_character_` 当成消息结束）

分配从 `FIRST` 起连续给号，顺序 = 字符首次出现的顺序（稳定、可复现）。
"""

import json

FIRST = 0x8940
LAST = 0x9FFC


def is_ok(code):
    lead, trail = code >> 8, code & 0xFF
    return (code >= 0x8800 and code <= LAST and trail != 0
            and ((0x81 <= lead <= 0x9F) or (0xE0 <= lead <= 0xFC)))


def assign(chars):
    """[字符] -> {字符: 码位}；跳过 ASCII 与已分配过的。"""
    out = {}
    code = FIRST
    for ch in chars:
        if ch in out or ord(ch) < 0x80:
            continue
        while not is_ok(code):
            code += 1
        out[ch] = code
        code += 1
    return out


def load(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    return {ch: int(code, 16) for ch, code in doc["chars"].items()}


def save(path, mapping, note):
    doc = {"note": note, "chars": {ch: "%04X" % code for ch, code in sorted(
        mapping.items(), key=lambda kv: kv[1])}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
