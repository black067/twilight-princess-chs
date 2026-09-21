import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import paths
import yaz0
import material
from patch_sjis_font import NAME_DEFAULT_BASE, NAME_DEFAULT_CHARS

MAP_JSON = os.path.join(paths.WORK, "sjis_map.json")
OUT_DIR = paths.parts_dir(paths.ORIGIN_VARIANT)   # 就地改写只出 origin 变体，文本部件落在它自己的目录

SHIFT_JIS_ENCODING = 3
TAG = 0x1A
ASCII_LO = 0x20
ASCII_HI = 0x7E
NEWLINE = 0x0A

# MSGTAG_REFMARK（group 6 / code 5）：引擎会插入 1 字节 CHAR_CODE_REFMARK = 0x89，
# 而 0x89 是 ShiftJIS 前导字节，会把下一个字符的首字节吞掉导致整行错位。
# 该 tag 只表示一个装饰性的 ※，直接换成字面 ※（U+203B）最稳。
REFMARK_TAG = 0x060005
REFMARK_CHAR = 0x203B

# 默认名改写表（id → 文本）。实机标定：897 = 主角默认名、898 = 马匹默认名；
# 899/900 是两屏标题，文本本来就对，不必改写。
# 表里的字写成 NAME_DEFAULT_CHARS 的单字节码位（码位表与理由在 patch_sjis_font.py）。
NAME_MSG_OVERRIDES = {
    897: "林克",
    898: "伊波娜",
}


def sections(blob):
    pos = 0x20
    out = []
    while pos + 8 <= len(blob):
        tag = blob[pos : pos + 4]
        if not tag.isalnum():
            break
        size = struct.unpack_from(">I", blob, pos + 4)[0]
        out.append((tag, pos, size))
        pos += size
        while pos % 0x20:
            pos += 1
    return out


def decode(blob, start, limit):
    """2 字节视角切 token。tag 几何实测：下一元素 = marker + size（size 含 2 字节 marker），
    payload = size - 6。"""
    out = []
    i = start
    while i + 1 < limit:
        cu = (blob[i] << 8) | blob[i + 1]
        if cu == 0:
            break
        if cu == 0x001A:
            if i + 3 > limit:
                break
            u_size = blob[i + 2]
            if u_size < 6 or i + u_size > limit:
                break
            out.append(("tag", bytes(blob[i + 3 : i + 6]), bytes(blob[i + 6 : i + u_size])))
            i += u_size
            continue
        out.append(("chr", cu))
        i += 2
    return out


def encode(tokens, remap):
    """引擎 ShiftJIS 路径：
    - tag：marker 改 1 字节 0x1A，size = payload + 5（引擎步进 = marker + size，
      传给 tag 处理器的 payload 长度 = size - 5）
    - 换行与 ASCII：改 1 字节（2 字节的 00 开头会被解码器当成码位 0 = 消息结束）
    - 其余码位：查映射表后按 2 字节写
    """
    out = bytearray()
    for token in tokens:
        if token[0] == "tag":
            _, tag_id, payload = token
            if int.from_bytes(tag_id, "big") == REFMARK_TAG:
                code = remap[REFMARK_CHAR]
                out += bytes((code >> 8, code & 0xFF))
                continue
            out.append(TAG)
            out.append(len(payload) + 5)
            out += tag_id
            out += payload
        else:
            code = token[1]
            if code == NEWLINE or ASCII_LO <= code <= ASCII_HI:
                out.append(code & 0xFF)
            else:
                new = remap.get(code, code)
                out += bytes((new >> 8, new & 0xFF))
    out.append(0)
    out.append(0)
    return bytes(out)


def message_slots(blob):
    """({DAT1 槽起点: token 列表}, [(消息下标, 槽起点)])：按生产几何切。

    原归档允许两条消息共用一段文本（后缀共享），所以按不同偏移切、按槽去重。
    """
    off = blob.find(b"MESG")
    size = struct.unpack_from(">I", blob, off + 8)[0]
    inner = blob[off : off + size]
    inf = next(s for s in sections(inner) if s[0] == b"INF1")
    dat = next(s for s in sections(inner) if s[0] == b"DAT1")
    nent, esize = struct.unpack_from(">HH", inner, inf[1] + 8)
    dat_abs = off + dat[1] + 8
    dat_end = off + dat[1] + dat[2]
    offsets = [struct.unpack_from(">I", inner, inf[1] + 0x10 + k * esize)[0] for k in range(nent)]
    starts = sorted(set(offsets))
    nxt = {}
    for i, s in enumerate(starts):
        nxt[s] = starts[i + 1] if i + 1 < len(starts) else dat_end - dat_abs
    texts = {}
    for s in starts:
        limit = dat_abs + nxt[s]
        texts[s] = decode(blob, dat_abs + s, limit - 2) if limit - (dat_abs + s) >= 2 else []
    return texts, [(k, o) for k, o in enumerate(offsets)]


def default_name_bytes(text):
    """默认名文本 → 单字节码位序列（配合字库里 NAME_DEFAULT_CHARS 的别名）。"""
    return bytes(NAME_DEFAULT_BASE + NAME_DEFAULT_CHARS.index(ch) for ch in text)


def patch_mesg(blob, remap, defaults=None):
    off = blob.find(b"MESG")
    size = struct.unpack_from(">I", blob, off + 8)[0]
    inner = blob[off : off + size]
    secs = sections(inner)
    inf = next(s for s in secs if s[0] == b"INF1")
    dat = next(s for s in secs if s[0] == b"DAT1")
    nent, esize = struct.unpack_from(">HH", inner, inf[1] + 8)
    dat_abs = off + dat[1] + 8
    dat_end = off + dat[1] + dat[2]

    blob[off + 0x10] = SHIFT_JIS_ENCODING

    offsets = sorted({struct.unpack_from(">I", inner, inf[1] + 0x10 + k * esize)[0]
                      for k in range(nent)})
    bounds = offsets[1:] + [dat_end - dat_abs]

    shrunk = exact = 0
    for old, bound in zip(offsets, bounds):
        start = dat_abs + old
        limit = dat_abs + bound
        if limit - start < 2:
            continue
        enc = encode(decode(blob, start, limit - 2), remap)
        assert len(enc) <= limit - start, "message does not fit its slot (off=%d)" % old
        if len(enc) < limit - start:
            shrunk += 1
        else:
            exact += 1
        blob[start : start + len(enc)] = enc
        for i in range(start + len(enc), limit):
            blob[i] = 0

    for msg_id, text in sorted((defaults or {}).items()):
        if msg_id >= nent:
            continue
        off_k = struct.unpack_from(">I", inner, inf[1] + 0x10 + msg_id * esize)[0]
        j = offsets.index(off_k)
        start = dat_abs + off_k
        limit = dat_abs + bounds[j]
        if isinstance(text, bytes):
            enc = text          # 已是目标编码的原始字节（默认名的单字节码位）
        else:
            enc = encode([("chr", ord(c)) for c in text], remap)
        assert len(enc) <= limit - start, "消息 %d 放不下：%r 需 %d 字节，槽位 %d" % (
            msg_id, text, len(enc), limit - start)
        blob[start : start + len(enc)] = enc
        for i in range(start + len(enc), limit):
            blob[i] = 0
        print("     改写 msg %d = %r（用 %d/%d 字节）" % (msg_id, text, len(enc), limit - start))

    return nent, len(offsets), shrunk, exact


def main():
    with open(MAP_JSON, encoding="utf-8") as f:
        doc = json.load(f)
    remap = {int(k, 16): int(v, 16) for k, v in doc["remap"].items()}
    # 默认名的单字节别名两个变体都有（见 patch_sjis_font.py 的 name_default_aliases）
    overrides = {k: default_name_bytes(v) for k, v in NAME_MSG_OVERRIDES.items()}

    os.makedirs(OUT_DIR, exist_ok=True)

    for base, arc in material.msg_arcs():
        blob = bytearray(arc)
        tail = base
        path = os.path.join(OUT_DIR, tail)
        if blob.find(b"MESG") < 0:
            with open(path, "wb") as f:
                f.write(yaz0.encode(bytes(blob)))
            print("  %-14s copied as-is" % tail)
            continue
        nent, msgs, shrunk, exact = patch_mesg(
            blob, remap, overrides if tail == "bmgres.arc" else None)
        with open(path, "wb") as f:
            f.write(yaz0.encode(bytes(blob)))
        print("  %-14s entries=%-5d msgs=%-5d shrunk=%-5d exact=%-5d size %d"
              % (tail, nent, msgs, shrunk, exact, len(blob)))


if __name__ == "__main__":
    main()
