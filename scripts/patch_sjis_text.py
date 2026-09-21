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
from build_cn_font import yaz0_encode
from extract_entry import extract
from extract_index import HEADER_LEN, decrypt_region
from list_index import entries

MAP_JSON = os.path.join(paths.WORK, "sjis_map.json")
OUT_DIR = os.path.join(paths.WORK, "sjis_parts")
TARGET_LANG = paths.msg_dir()

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

# 默认名字的改写表（id → 文本）。
#
# 编号已由实机标定（给四个候选消息各写一个唯一标记，跑一次看落点）：
#   897 槽 6 字节  = 主角默认名（第 1 屏名字框）
#   898 槽 8 字节  = 马匹默认名（第 2 屏名字框）
#   899 槽 14 字节 = 马匹界面标题（第 2 屏标题）
#   900 槽 10 字节 = 主角界面标题（第 1 屏标题）
# 即引擎用的编号跟官中文本自身的编号一致，899/900 的官中文本
# （输入马匹名称 / 输入名称）本来就正确，不必改写。
#
# 默认名必须**每个字一个单字节**：EU 的 d_name_c::NameStrSet 每次只取 1 字节
# （`mChrInfo[i].mCharacter = static_cast<u8>(*moji); moji++;`），而 setNameText()
# 又把这个字节单独 `%c` 塞进 J2DTextBox；官中的「林克」是 2 字节码位，被拆成两个假字
# 后，前导字节还会把紧随的 ESC(0x1B) 当成尾字节吞掉 → 名字框乱码（实机已确认）。
# 0xA0..0xDF 在 ShiftJIS 里不是前导字节（JUTFont::isLeadByte_ShiftJIS 只看
# 0x81..0x9F / 0xE0..0xFC），字体路径与消息路径都把它当完整码位 ⇒ 用
# patch_sjis_font.py 里的 NAME_DEFAULT_CHARS 单字节别名（0xA1.. = 林 克 伊 波 娜），
# 默认名就能是中文且到处都显示正确（名字框 / 对话 / 存档界面共用同一套字节）。
# 只在 open 模式（字库带这些别名）下改写；original 模式保留官中原文做字节回归。
NAME_DEFAULT_CHARS = "林克伊波娜"
NAME_DEFAULT_BASE = 0x00A1
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
    # 默认名的单字节别名只存在于 open 模式字库里（见 patch_sjis_font.py）。
    source = paths.option("--glyph-source") or "original"
    overrides = None
    if source.startswith("open"):
        overrides = {k: default_name_bytes(v) for k, v in NAME_MSG_OVERRIDES.items()}
    else:
        print("  glyph-source=original：不改默认名（保持官中原文）")

    pak = paths.pak()
    with open(pak, "rb") as f:
        head = f.read(HEADER_LEN)
        size1 = struct.unpack_from("<I", head, 0x18)[0]
        index = decrypt_region(f, HEADER_LEN, size1, "header")
    recs = entries(index)
    data_start = HEADER_LEN + len(index)
    os.makedirs(OUT_DIR, exist_ok=True)

    for name in [x[0] for x in recs if x[0].startswith("res/Msgcn/")]:
        r = next(x for x in recs if x[0] == name)
        blob = bytearray(yaz0.decompress(extract(pak, data_start, name, r[1], r[3])))
        tail = name.split("/")[-1]
        path = os.path.join(OUT_DIR, ("res_%s_%s" % (TARGET_LANG, tail)).replace("/", "_"))
        if blob.find(b"MESG") < 0:
            with open(path, "wb") as f:
                f.write(yaz0_encode(bytes(blob)))
            print("  %-14s copied as-is" % tail)
            continue
        nent, msgs, shrunk, exact = patch_mesg(
            blob, remap, overrides if tail == "bmgres.arc" else None)
        with open(path, "wb") as f:
            f.write(yaz0_encode(bytes(blob)))
        print("  %-14s entries=%-5d msgs=%-5d shrunk=%-5d exact=%-5d size %d"
              % (tail, nent, msgs, shrunk, exact, len(blob)))


main()
