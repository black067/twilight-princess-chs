"""码位分配：给译文用到的字符分配新码位，不依赖原字库的码位表。

分配在可用区里连续给号，顺序 = 字符首次出现的顺序（稳定、可复现）。
"""

import json
import os

# 可用码位区间：JIS X 0208 未定义行（89–94 行与行外空区），除了这些标准区域都留给游戏自己
RANGES = ((0xEAA5, 0xEFFC), (0xF040, 0xF9FC))

TRAIL_LO, TRAIL_HI = 0x40, 0xFC


def reserved(data_dir):
    """引擎自己会查的码位（名字键盘 `l_mojiZh` 的表）：不能分给译文。"""
    with open(os.path.join(data_dir, "name_keyboard.json"), encoding="utf-8") as f:
        return {int(c, 16) for c in json.load(f)["codes"]}


def is_ok(code, skip=()):
    lead, trail = code >> 8, code & 0xFF
    return (any(lo <= code <= hi for lo, hi in RANGES)
            and ((0x81 <= lead <= 0x9F) or (0xE0 <= lead <= 0xFC))
            and (TRAIL_LO <= trail <= TRAIL_HI) and trail != 0x7F
            and code not in skip)


def assign(chars, skip=()):
    """[字符] -> {字符: 码位}；跳过 ASCII 与已分配过的。"""
    out = {}
    pool = (c for lo, hi in RANGES for c in range(lo, hi + 1) if is_ok(c, skip))
    for ch in chars:
        if ch in out or ord(ch) < 0x80:
            continue
        out[ch] = next(pool)
    return out


def load(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    return {ch: int(code, 16) for ch, code in doc["chars"].items()}


def save(path, mapping, note):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = {"note": note, "chars": {ch: "%04X" % code for ch, code in sorted(
        mapping.items(), key=lambda kv: kv[1])}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
