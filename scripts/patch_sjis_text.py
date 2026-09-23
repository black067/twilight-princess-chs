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
import patch_sjis_font as PSF
import text_resources as TR

MAP_JSON = paths.sjis_map_json()
OUT_DIR = paths.parts_dir(paths.ORIGIN_VARIANT)   # 改现成素材只出 origin 变体，文本资源写在它自己的目录

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


def decode(blob, start, limit, encoding=2):
    """按源素材的 encoding 切 token。tag 几何实测：当前字符宽度的 marker `0x1A` + 1 字节 size
    + 3 字节 tag id + payload，步进 = size（payload = size - 4 - marker 宽度）。
    """
    out = []
    i = start
    while i < limit:
        code, width = read_char(blob, i, limit, encoding)
        if code is None:
            break
        if code == 0:
            break
        if code == TAG:
            size = blob[i + width]
            if size < 4 + width or i + size > limit:
                break
            out.append(("tag", bytes(blob[i + width + 1 : i + width + 4]),
                        bytes(blob[i + width + 4 : i + size])))
            i += size
            continue
        out.append(("chr", code))
        i += width
    return out


def encoding_of(blob):
    """BMG 头里的 encoding（1 = 每字节一个字符，2 = 2 字节码位，3 = ShiftJIS）。"""
    return blob[blob.find(b"MESG") + 0x10]


def is_lead(byte):
    return 0x81 <= byte <= 0x9F or 0xE0 <= byte <= 0xFC


def read_char(blob, i, limit, encoding):
    """(码位, 宽度)：按源编码取一个字符；越界返回 (None, 0)。"""
    if encoding == 2:
        if i + 1 >= limit:
            return None, 0
        return (blob[i] << 8) | blob[i + 1], 2
    if encoding == 1:
        return blob[i], 1
    if is_lead(blob[i]):
        if i + 1 >= limit:
            return None, 0
        return ord(blob[i : i + 2].decode("shift_jis")), 2
    return ord(blob[i : i + 1].decode("shift_jis")), 1


def pool_tokens(pool, at, encoding):
    """STR1 池里的一个串 -> token 列表（读到 0 结束，编码与它所在 BMG 相同）。"""
    out = []
    i = at
    while i < len(pool):
        code, width = read_char(pool, i, len(pool), encoding)
        if code is None or code == 0:
            break
        out.append(("chr", code))
        i += width
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
    """({DAT1 文本起点: token 列表}, [(消息下标, 文本起点)])：按生产几何切。

    原归档允许两条消息共用一段文本（后缀共享），所以按不同偏移切、按文本起点去重。
    """
    encoding = encoding_of(blob)
    width = 2 if encoding == 2 else 1
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
        texts[s] = (decode(blob, dat_abs + s, limit - width, encoding)
                    if limit - (dat_abs + s) >= width else [])
    return texts, [(k, o) for k, o in enumerate(offsets)]


def default_name_bytes(text):
    """默认名文本 → 单字节码位序列（配合字库里 default_name_chars 的别名）。"""
    chars = PSF.name_default_chars()
    missing = [ch for ch in text if ch not in chars]
    if missing:
        sys.exit("默认名 %r 里有本地化方案 default_name_chars 没收的字：%s" % (text, missing))
    return bytes(PSF.NAME_DEFAULT_BASE + chars.index(ch) for ch in text)


def name_cells(inner, resource):
    """{条目下标: 译表 key}：配置里要按单字节码位写的条目（按消息号表对号）。"""
    wanted = set(PSF.default_name_cells())
    if not wanted:
        return {}
    mid = next((s for s in sections(inner) if s[0] == b"MID1"), None)
    if not mid:
        return {}
    count = struct.unpack_from(">H", inner, mid[1] + 8)[0]
    ids = list(struct.unpack_from(">%dI" % count, inner, mid[1] + 0x10))
    return {k: key for k, key in enumerate(TR.message_keys(resource, ids)) if key in wanted}


def patch_mesg(blob, remap, resource=""):
    off = blob.find(b"MESG")
    size = struct.unpack_from(">I", blob, off + 8)[0]
    inner = blob[off : off + size]
    secs = sections(inner)
    inf = next(s for s in secs if s[0] == b"INF1")
    dat = next(s for s in secs if s[0] == b"DAT1")
    nent, esize = struct.unpack_from(">HH", inner, inf[1] + 8)
    dat_abs = off + dat[1] + 8
    dat_end = off + dat[1] + dat[2]

    encoding = encoding_of(blob)
    width = 2 if encoding == 2 else 1
    blob[off + 0x10] = SHIFT_JIS_ENCODING

    offsets = sorted({struct.unpack_from(">I", inner, inf[1] + 0x10 + k * esize)[0]
                      for k in range(nent)})
    bounds = offsets[1:] + [dat_end - dat_abs]

    targets = name_cells(inner, resource)
    # 文本必须在改写前从源字节解出：改写把码位换成了目标编码，再解就是乱码
    wanted = {}
    for idx, key in sorted(targets.items()):
        off_k = struct.unpack_from(">I", inner, inf[1] + 0x10 + idx * esize)[0]
        limit = dat_abs + bounds[offsets.index(off_k)]
        start = dat_abs + off_k
        wanted[idx] = "".join(chr(t[1]) for t in decode(blob, start, limit - width, encoding)
                              if t[0] == "chr")

    shrunk = exact = 0
    for old, bound in zip(offsets, bounds):
        start = dat_abs + old
        limit = dat_abs + bound
        if limit - start < width:
            continue
        enc = encode(decode(blob, start, limit - width, encoding), remap)
        assert len(enc) <= limit - start, "message does not fit its slot (off=%d)" % old
        if len(enc) < limit - start:
            shrunk += 1
        else:
            exact += 1
        blob[start : start + len(enc)] = enc
        for i in range(start + len(enc), limit):
            blob[i] = 0

    for idx, key in sorted(targets.items()):
        off_k = struct.unpack_from(">I", inner, inf[1] + 0x10 + idx * esize)[0]
        j = offsets.index(off_k)
        start = dat_abs + off_k
        limit = dat_abs + bounds[j]
        text = wanted[idx]
        enc = default_name_bytes(text)
        assert len(enc) <= limit - start, "消息 %d 放不下：%r 需 %d 字节，可用 %d" % (
            idx, text, len(enc), limit - start)
        blob[start : start + len(enc)] = enc
        for i in range(start + len(enc), limit):
            blob[i] = 0
        print("     改写 %s = %r（用 %d/%d 字节）" % (key, text, len(enc), limit - start))

    return nent, len(offsets), shrunk, exact


def main():
    with open(MAP_JSON, encoding="utf-8") as f:
        doc = json.load(f)
    remap = {int(k, 16): int(v, 16) for k, v in doc["remap"].items()}

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
        inner_name = next(name for name in material.rarc_files(arc) if b"MESG" in material.rarc_files(arc)[name])
        resource = os.path.splitext(inner_name)[0]
        nent, msgs, shrunk, exact = patch_mesg(blob, remap, resource)
        with open(path, "wb") as f:
            f.write(yaz0.encode(bytes(blob)))
        print("  %-14s entries=%-5d msgs=%-5d shrunk=%-5d exact=%-5d size %d"
              % (tail, nent, msgs, shrunk, exact, len(blob)))


if __name__ == "__main__":
    main()
