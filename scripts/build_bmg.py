"""从零生成消息归档：RARC 与 BMG 全部自己写，只吃「索引表 + 形状表 + 译文」。

输入
  data/msg_index.<lang>.json 容器索引（BMG 名、条数、entrySize、MID1、条目属性、尾部块）
  data/text_resources.json   文本资源形状（哪些资源、每格叫什么）
  cn/texts.csv               译文（`key` + `zh-Hans`）
  原样带过的块               FLW1/FLI1 流脚本（无正文文本）

输出
  work/scratch_parts/bmgres*.arc   Yaz0 压的 RARC，可直接被 build_sjis_pack.py 打包
  work/code_map.json               字符 -> 新码位（字库生成器读同一份）

自己写的东西：MESG 头、INF1（每条 = 偏移 + message_id + 属性，见 docs「消息属性」）、
DAT1（布局自定）、MID1（消息号列表）、STR1（短串表的字符串池）、RARC（含名字哈希）。
"""

import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import codes
import material
import paths
import patch_sjis_font as PSF
import patch_sjis_text as PST
import rarc
import text_resources as TR
import texts
import yaz0

CODE_JSON = paths.code_map_json()
ENCODING = 3

TEXTS = paths.cli("--texts") or texts.file()
SPACE = paths.code_space()                     # own=自分配码位；sjis=沿用现有字库的码位
OUT_DIR = paths.scratch_dir(SPACE)


def block(tag, payload):
    """段 = tag + u32 段长 + 载荷，段长按 0x20 对齐。"""
    raw = 8 + len(payload)
    size = rarc.align_up(raw)
    return tag + struct.pack(">I", size) + payload + b"\x00" * (size - raw)


def build_messages(src, spec, resource, rows, remap, default_names=False):
    """重建消息表：正文按 texts.csv 重排（每条一个槽），属性来自索引，尾部块原样接上。"""
    n, esize = spec["entries"], spec["entrySize"]
    ids = spec["mid1"]
    assert len(ids) == n, (len(ids), n)
    attrs = expand_attrs(spec)                  # 条目属性（说话人/框样式/文字速度…）
    assert esize == 6 + len(attrs[0]), (esize, len(attrs[0]))
    names = PSF.name_default_chars() if default_names else ""
    keys = TR.message_keys(resource, ids)
    name_cells = set(PSF.default_name_cells())

    dat = bytearray()
    offsets = []
    for k in range(n):
        tokens = texts.parse_literal(rows[keys[k]])
        offsets.append(len(dat))
        if names and keys[k] in name_cells:
            # 名字框逐字节取字，默认名写单字节码位（见 docs「名字与键盘」）
            dat += PST.default_name_bytes("".join(chr(t[1]) for t in tokens if t[0] == "chr"))
            dat += b"\x00\x00"
        else:
            dat += PST.encode(tokens, remap)

    inf = b"".join(struct.pack(">IH", offsets[k], ids[k]) + attrs[k] for k in range(n))
    body = block(b"INF1", struct.pack(">HH", n, esize) + b"\x00" * 4 + inf)
    body += block(b"DAT1", bytes(dat))
    mid = struct.pack(">HBB", n, 0, 0) + b"\x00" * 4 + b"".join(struct.pack(">I", i) for i in ids)
    body += block(b"MID1", mid)

    # 尾部块：按表逐个核对 tag/长度后原样接上（无正文文本，见 docs）
    # 原归档的文件项尺寸比块表小几个字节（末块的对齐留白落在文件区域外），缺的用 0 补
    tail_len = sum(t["size"] for t in spec.get("tails", []))
    tail = src[spec["bmgSize"] : spec["bmgSize"] + tail_len]
    if len(tail) < tail_len:
        assert tail_len - len(tail) < 0x20, (len(tail), tail_len)
        tail += b"\x00" * (tail_len - len(tail))
    p = 0
    for t in spec.get("tails", []):
        assert tail[p : p + 4] == t["tag"].encode(), (t["tag"], tail[p : p + 4])
        assert struct.unpack_from(">I", tail, p + 4)[0] == t["size"]
        p += t["size"]

    blocks = 3 + len(spec.get("tails", []))
    head = (b"MESG" + b"bmg1" + struct.pack(">II", len(body), blocks)
            + bytes((ENCODING,)) + b"\x00" * 15)
    return head + body + tail


def build_unit(src, spec, resource, shape, rows, remap):
    """重建短串表：STR1 自排，条目保留原有字段，只换两个字符串偏移。

    标签由引擎拼成 `"%d %s"` 插进消息串（`dMsgUnit_c::setTag`），所以跟正文一样编码：
    ASCII 与换行 1 字节、其余查码位表后 2 字节，`0000` 收尾。
    """
    secs = dict((t, (o, s)) for t, o, s in PST.sections(src))
    inf, dat, str1 = secs.get(b"INF1"), secs.get(b"DAT1"), secs.get(b"STR1")
    if not (inf and dat and str1) or shape.get("pool") != "STR1":
        sys.exit("%s 的形状与归档不符（string_pairs 需要 INF1 + DAT1 + STR1）" % resource)
    n, esize = struct.unpack_from(">HH", src, inf[0] + 8)
    assert n == spec["entries"], (n, spec["entries"])

    pool = bytearray()
    entries = bytearray()
    for k in range(n):
        fields = list(struct.unpack_from(">" + "H" * (esize // 2), src, inf[0] + 0x10 + k * esize))
        for name, field in shape["cells"].items():
            tokens = texts.parse_literal(rows["%s/%d/%s" % (resource, k, name)])
            fields[field] = len(pool)
            pool += PST.encode(tokens, remap)
        entries += struct.pack(">" + "H" * (esize // 2), *fields)

    body = block(b"INF1", struct.pack(">HH", n, esize) + b"\x00" * 4 + bytes(entries))
    body += block(b"DAT1", src[dat[0] + 8 : dat[0] + dat[1]])
    body += block(b"STR1", bytes(pool))
    head = (b"MESG" + b"bmg1" + struct.pack(">II", len(body), 3)
            + bytes((src[0x10],)) + b"\x00" * 15)
    return head + body


def expand_attrs(spec):
    """每条消息的属性字节（表里存去重表 + 游程）。"""
    pool = [bytes.fromhex(h) for h in spec["attrs"]]
    runs = spec["attrRuns"]
    out = []
    for i in range(0, len(runs), 2):
        out += [pool[runs[i]]] * runs[i + 1]
    assert len(out) == spec["entries"], (len(out), spec["entries"])
    return out


def slot_index(src, spec):
    """[(消息下标, DAT1 槽起点)]：从源文件里读 INF1 的偏移列。"""
    off = src.find(b"MESG")
    size = struct.unpack_from(">I", src, off + 8)[0]
    inner = src[off : off + size]
    inf = next(s for s in PST.sections(inner) if s[0] == b"INF1")
    nent, esize = struct.unpack_from(">HH", inner, inf[1] + 8)
    return [(k, struct.unpack_from(">I", inner, inf[1] + 0x10 + k * esize)[0])
            for k in range(nent)]


def self_check(raw, spec, shapes):
    """生成后自检：按引擎的取法验证 RARC 与 BMG。"""
    if not spec["files"]:
        return
    hlen, fdoff = struct.unpack_from(">I", raw, 8)[0], struct.unpack_from(">I", raw, 0x0C)[0]
    _, _, nfiles, fileoff, stlen, stoff = struct.unpack_from(">IIIIII", raw, 0x20)
    strtab = raw[0x20 + stoff : 0x20 + stoff + stlen]
    data = 0x20 + fdoff
    found = {}
    for i in range(nfiles):
        o = 0x20 + fileoff + i * 0x14
        fid, nh, tfno, doff, dsize = struct.unpack_from(">HHIII", raw, o)
        if tfno >> 24 != 0x11:
            continue
        noff = tfno & 0xFFFFFF
        end = strtab.find(b"\x00", noff)
        assert end >= 0, "文件名字符串越界：name_off=%#x" % noff
        nm = strtab[noff:end].decode()
        assert nh == rarc.name_hash(nm), "名字哈希不对：%s" % nm
        found[nm] = raw[data + doff : data + doff + dsize]
    for f in spec["files"]:
        assert f["name"] in found, "归档里取不到 %s" % f["name"]
        if "entries" not in f:
            continue
        blob = found[f["name"]]
        assert blob.find(b"MESG") == 0, "%s 不是 BMG" % f["name"]
        shape = shapes[os.path.splitext(f["name"])[0]]["shape"]
        p, n, esize, ids, dat1, pool = 0x20, None, None, None, None, None
        while p + 8 <= len(blob):
            tag = blob[p : p + 4]
            if not tag.isalnum():
                break
            size = struct.unpack_from(">I", blob, p + 4)[0]
            if tag == b"INF1":
                n, esize = struct.unpack_from(">HH", blob, p + 8)
                assert (n, esize) == (f["entries"], f["entrySize"]), "INF1 头不对"
            if tag == b"DAT1":
                dat1 = size - 8
            if tag == b"STR1":
                pool = size - 8
            if tag == b"MID1":
                num = struct.unpack_from(">H", blob, p + 8)[0]
                ids = list(struct.unpack_from(">%dI" % num, blob, p + 16))
            p += size
            while p % 0x20:
                p += 1
        inf = blob.find(b"INF1")
        esize_h = esize // 2
        if shape == "messages":
            assert ids == f["mid1"], "%s 的 MID1 与表不一致" % f["name"]
            attrs = expand_attrs(f)
            for k in range(n):
                off, eid = struct.unpack_from(">IH", blob, inf + 0x10 + k * esize)[0:2]
                assert off < dat1, "%s 第 %d 条的 DAT1 偏移越界" % (f["name"], k)
                assert eid == ids[k], "%s 第 %d 条的 message_id 与 MID1 不一致" % (f["name"], k)
                assert blob[inf + 0x10 + k * esize + 6 : inf + 0x10 + (k + 1) * esize] == attrs[k], \
                    "%s 第 %d 条的属性字节不对" % (f["name"], k)
        else:
            assert ids is None and pool, "%s 不应有 MID1 而应有 STR1" % f["name"]
            for k in range(n):
                fields = struct.unpack_from(">" + "H" * esize_h, blob, inf + 0x10 + k * esize)
                for field in range(2, esize_h):
                    assert fields[field] < pool, \
                        "%s 第 %d 条的字符串偏移越界" % (f["name"], k)


def main():
    index, shapes = TR.load()
    rows = texts.read(TEXTS)
    cells = TR.cells(index, shapes)
    expected = [key for _, _, _, _, key in cells]
    unknown = sorted(set(rows) - set(expected))
    missing = [key for key in expected if key not in rows]
    if missing or unknown:
        sys.exit("texts.csv 与索引不符：缺 %d 条%s；多 %d 条%s"
                 % (len(missing), "（%s）" % "、".join(missing[:3]) if missing else "",
                    len(unknown), "（%s）" % "、".join(unknown[:3]) if unknown else ""))

    sources = dict(material.msg_arcs())
    for base in index:
        if base not in sources:
            sys.exit("cn/msg/ 里缺 %s" % base)
    blobs = {}
    for base, arc in sources.items():
        for name, data in material.rarc_files(arc).items():
            blobs[(base, name)] = data

    # ---- 第一遍：收集要编码的字符（译文 + 图标别名 + 默认名 + ※ + 键盘字表）
    chars, seen = [], set()

    def need(ch):
        if ch not in seen:
            seen.add(ch)
            chars.append(ch)

    for key in expected:
        for tok in texts.parse_literal(rows[key]):
            if tok[0] == "chr" and tok[1] >= 0x80:
                need(chr(tok[1]))
    for ch in PSF.ICON_ALIAS.values():
        need(chr(ch))
    for ch in PSF.name_default_chars():
        need(ch)
    need(chr(PST.REFMARK_CHAR))
    with open(os.path.join(paths.DATA, "name_keyboard.json"), encoding="utf-8") as f:
        for c in json.load(f)["codes"]:
            code = int(c, 16)
            try:
                need(bytes((code >> 8, code & 0xFF)).decode("shift_jis"))
            except UnicodeDecodeError:
                pass

    mapping = codes.assign(chars, codes.reserved(paths.DATA))
    codes.save(CODE_JSON, mapping, "译文与控制字符 -> 新码位（%d 个）" % len(mapping))
    print("码位：%d 个字 %#x..%#x -> %s"
          % (len(mapping), min(mapping.values()), max(mapping.values()), CODE_JSON))
    if SPACE == "own":
        remap = {ord(ch): code for ch, code in mapping.items()}
    else:
        # 沿用现有字库的码位空间（`sjis_map.py` 的 remap：原码位 -> 现有字库的码位）
        with open(paths.sjis_map_json(), encoding="utf-8") as f:
            remap = {int(k, 16): int(v, 16) for k, v in json.load(f)["remap"].items()}
        print("码位空间：%s（沿用现有字库 %d 条重映射）" % (SPACE, len(remap)))

    # ---- 第二遍：逐归档重建
    os.makedirs(OUT_DIR, exist_ok=True)
    for base, spec in sorted(index.items()):
        w = rarc.Writer(os.path.splitext(base)[0])
        for f in spec["files"]:
            if "entries" not in f:
                w.add(f["name"], blobs[(base, f["name"])])
                continue
            resource = os.path.splitext(f["name"])[0]
            shape = shapes[resource]
            src = blobs[(base, f["name"])]
            if shape["shape"] == "messages":
                w.add(f["name"], build_messages(src, f, resource, rows, remap,
                                                default_names=(f["name"] == "zel_00.bmg")))
            elif shape["shape"] == "string_pairs":
                w.add(f["name"], build_unit(src, f, resource, shape, rows, remap))
            else:
                sys.exit("不认识的形状 %r（%s）" % (shape["shape"], resource))
        out = os.path.join(OUT_DIR, base)
        raw = w.build()
        self_check(raw, spec, shapes)
        with open(out, "wb") as fh:
            fh.write(yaz0.encode(raw))
        print("  %-14s %d 文件 -> %d 字节" % (base, len(spec["files"]), os.path.getsize(out)))


main()
