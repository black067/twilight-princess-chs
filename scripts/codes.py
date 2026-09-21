"""码位分配：给译文用到的字符分配新码位，不依赖原字库的码位表。

引擎对码位的四条要求（`patch_sjis_font.py` 的「修法」与 `docs/技术备忘.md`）：
  1. 首字节是合法前导：0x81–0x9F / 0xE0–0xFC（`isLeadByte_ShiftJIS`）
  2. 码位 ≥ 0x8800，否则被 `change1ByteTo2Bytes` / `changeKataToHira` 改写
  3. 尾字节是合法的 Shift-JIS 尾字节：0x40–0x7E / 0x80–0xFC。
     低字节 0x00 会被 `process_character_` 当成消息结束；0x1A 会被 `getStringKanji` /
     `getStringKana` 当成标签标记、0x1B 会被 `J2DPrint::parse` 当成控制码——
     这几处都是**逐字节**扫的，会把码位拆坏
  4. 落在 JIS X 0208 未定义区（`0xEAA5–0xEFFC` / `0xF040–0xF9FC`）：游戏自己的数据、
     菜单资源里都是标准 Shift-JIS 字符，这些码位不会被它们用到，否则同一个码位会有两种含义
     （实测：名字框空位的占位码撞上译文码位就画出怪字）
  5. 码位不是 `reserved()` 报的那批（引擎名字键盘自己会查）

分配在可用区里从小到大连续给号，顺序 = 字符首次出现的顺序（稳定、可复现）。
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
    doc = {"note": note, "chars": {ch: "%04X" % code for ch, code in sorted(
        mapping.items(), key=lambda kv: kv[1])}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
