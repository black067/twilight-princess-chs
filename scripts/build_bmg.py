"""从零生成消息归档：RARC 与 BMG 全部自己写，只吃「索引表 + 译文」。

输入
  data/msg_index.json     容器索引（BMG 名、条数、entrySize、groupID、MID1、条目属性、尾部块）
  译文                     从输入归档按生产几何解码（`patch_sjis_text` 的口径）
  原样带过的两块           FLW1/FLI1 流脚本（无正文文本）、zel_unit.bmg 单位标签表

输出
  work/scratch_parts/bmgres*.arc   Yaz0 压的 RARC，可直接被 build_sjis_pack.py 打包
  work/code_map.json               字符 -> 新码位（字库生成器读同一份）

自己写的东西：MESG 头、INF1（每条 = 偏移 + message_id + 属性，见 docs「消息属性」）、
DAT1（布局自定，不再受原始槽位容量限制）、MID1（消息号列表）、RARC（含名字哈希）。
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
import yaz0

INDEX_JSON = os.path.join(paths.DATA, "msg_index.json")
CODE_JSON = os.path.join(paths.WORK, "code_map.json")
ENCODING = 3
PASSTHROUGH = ("zel_unit.bmg",)   # 原样带过：单位标签表（15 组短串），见 docs

SPACE = paths.cli("--code-space") or "own"     # own=自分配码位；sjis=沿用现有字库的码位
OUT_DIR = os.path.join(paths.WORK, "scratch_parts" if SPACE == "own" else "scratch_parts.%s" % SPACE)


def rarc_files(arc):
    """{归档内文件名: 数据}。"""
    hlen, fdoff = struct.unpack_from(">I", arc, 8)[0], struct.unpack_from(">I", arc, 0x0C)[0]
    _, _, nfiles, fileoff, stlen, stoff = struct.unpack_from(">IIIIII", arc, 0x20)
    strtab = arc[0x20 + stoff : 0x20 + stoff + stlen]
    data = 0x20 + fdoff
    out = {}
    for i in range(nfiles):
        o = 0x20 + fileoff + i * 0x14
        fid, nh, tfno, doff, dsize = struct.unpack_from(">HHIII", arc, o)
        if tfno >> 24 != 0x11:
            continue
        noff = tfno & 0xFFFFFF
        name = strtab[noff : strtab.index(b"\x00", noff)].decode()
        out[name] = arc[data + doff : data + doff + dsize]
    return out


def slots(blob):
    """({DAT1 槽起点: token 列表}, [(消息下标, 槽起点)])：按生产几何切。"""
    off = blob.find(b"MESG")
    size = struct.unpack_from(">I", blob, off + 8)[0]
    inner = blob[off : off + size]
    inf = next(s for s in PST.sections(inner) if s[0] == b"INF1")
    dat = next(s for s in PST.sections(inner) if s[0] == b"DAT1")
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
        texts[s] = PST.decode(blob, dat_abs + s, limit - 2) if limit - (dat_abs + s) >= 2 else []
    return texts, [(k, o) for k, o in enumerate(offsets)]


def build_file(src, spec, texts, remap, default_names=False):
    """重建一个 BMG 文件：正文块自造，尾部块（FLW1/FLI1）原样接上。"""
    idx = slot_index(src, spec)                 # [(消息下标, DAT1 槽起点)]
    n, esize = spec["entries"], spec["entrySize"]

    # MID1：每个消息的全局消息号列表（表里的纯数字）。子头 8 字节：条数(u16) + form/supplement(u16) + 4 字节填充
    ids = spec["mid1"]
    assert len(ids) == n, (len(ids), n)
    mid = struct.pack(">HBB", n, 0, 0) + b"\x00" * 4 + b"".join(struct.pack(">I", i) for i in ids)
    attrs = expand_attrs(spec)                  # 条目属性（说话人/框样式/文字速度…）
    assert esize == 6 + len(attrs[0]), (esize, len(attrs[0]))

    # 默认名（主角/马）走单字节码位：名字框逐字节取字，两字节码位会被拆坏（见 docs「名字与键盘」）
    overrides = ({k: PST.default_name_bytes(v) for k, v in PST.NAME_MSG_OVERRIDES.items()}
                 if default_names else {})

    shared = {}                                 # 源槽起点 -> 新槽起点（未被覆盖的消息共享）
    per_msg = {}                                # 消息号 -> 新槽起点（默认名单独占槽）
    dat = bytearray()
    for k, o in idx:
        if k in overrides:
            per_msg[k] = len(dat)
            dat += overrides[k] + b"\x00\x00"
            continue
        if o not in shared:
            shared[o] = len(dat)
            dat += PST.encode(texts[o], remap)

    def slot_at(k, o):
        return per_msg[k] if k in per_msg else shared.get(o, 0)

    inf = bytearray()
    assert len(idx) == n, (len(idx), n)
    for k, o in idx:
        inf += struct.pack(">IH", slot_at(k, o), ids[k]) + attrs[k]

    def block(tag, payload):
        raw = 8 + len(payload)
        size = rarc.align_up(raw)
        return tag + struct.pack(">I", size) + payload + b"\x00" * (size - raw)

    body = block(b"INF1", struct.pack(">HH", n, esize) + b"\x00" * 4 + bytes(inf))
    body += block(b"DAT1", bytes(dat))
    if mid:
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

    blocks = 2 + (1 if mid else 0) + len(spec.get("tails", []))
    head = (b"MESG" + b"bmg1" + struct.pack(">II", len(body), blocks)
            + bytes((ENCODING,)) + b"\x00" * 15)
    return head + body + tail


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


def self_check(raw, spec):
    """生成后自检：按引擎的取法验证 RARC 与 BMG（这次两个 bug 都该被它拦住）。"""
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
        blob = found[f["name"]]
        if "entries" not in f or f["name"] in PASSTHROUGH:
            continue
        assert blob.find(b"MESG") == 0, "%s 不是 BMG" % f["name"]
        p, n, esize, ids, dat1 = 0x20, None, None, None, None
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
            if tag == b"MID1":
                num = struct.unpack_from(">H", blob, p + 8)[0]
                ids = list(struct.unpack_from(">%dI" % num, blob, p + 16))
            p += size
            while p % 0x20:
                p += 1
        assert ids == f["mid1"], "%s 的 MID1 与表不一致" % f["name"]
        inf = blob.find(b"INF1")
        attrs = expand_attrs(f)
        for k in range(n):
            off, eid = struct.unpack_from(">IH", blob, inf + 0x10 + k * esize)[0:2]
            assert off < dat1, "%s 第 %d 条的 DAT1 偏移越界" % (f["name"], k)
            assert eid == ids[k], "%s 第 %d 条的 message_id 与 MID1 不一致" % (f["name"], k)
            assert blob[inf + 0x10 + k * esize + 6 : inf + 0x10 + (k + 1) * esize] == attrs[k], \
                "%s 第 %d 条的属性字节不对" % (f["name"], k)


def main():
    with open(INDEX_JSON, encoding="utf-8") as f:
        table = json.load(f)
    sources = dict(material.msg_arcs())

    # ---- 第一遍：收集要编码的字符（译文 + 图标别名 + 默认名 + ※ + 键盘字表）
    chars, seen = [], set()

    def need(ch):
        if ch not in seen:
            seen.add(ch)
            chars.append(ch)

    all_texts = {}
    for base, spec in table.items():
        if base not in sources:
            continue
        files = rarc_files(sources[base])
        for f in spec["files"]:
            if f["name"] in PASSTHROUGH or "entries" not in f or f["name"] not in files:
                continue
            texts, _ = slots(files[f["name"]])
            all_texts[(base, f["name"])] = texts
            for toks in texts.values():
                for tok in toks:
                    if tok[0] == "chr" and tok[1] >= 0x80:
                        need(chr(tok[1]))
    for ch in PSF.ICON_ALIAS.values():
        need(chr(ch))
    for ch in PSF.NAME_DEFAULT_CHARS:
        need(ch)
    need(chr(PST.REFMARK_CHAR))
    with open(os.path.join(paths.DATA, "name_keyboard.json"), encoding="utf-8") as f:
        for c in json.load(f)["codes"]:
            code = int(c, 16)
            try:
                need(bytes((code >> 8, code & 0xFF)).decode("shift_jis"))
            except UnicodeDecodeError:
                pass

    mapping = codes.assign(chars)
    codes.save(CODE_JSON, mapping, "译文与控制字符 -> 新码位（%d 个）" % len(mapping))
    print("码位：%d 个字 %#x..%#x -> %s"
          % (len(mapping), min(mapping.values()), max(mapping.values()), CODE_JSON))
    if SPACE == "own":
        remap = {ord(ch): code for ch, code in mapping.items()}
    else:
        # 沿用现有字库的码位空间（`sjis_map.py` 的 remap：原码位 -> 现有字库的码位）
        with open(os.path.join(paths.WORK, "sjis_map.json"), encoding="utf-8") as f:
            remap = {int(k, 16): int(v, 16) for k, v in json.load(f)["remap"].items()}
        print("码位空间：%s（沿用现有字库 %d 条重映射）" % (SPACE, len(remap)))

    # ---- 第二遍：逐归档重建
    os.makedirs(OUT_DIR, exist_ok=True)
    for base, spec in sorted(table.items()):
        files = rarc_files(sources[base]) if base in sources else {}
        w = rarc.Writer(os.path.splitext(base)[0])
        for f in spec["files"]:
            if f["name"] in PASSTHROUGH or "entries" not in f:
                w.add(f["name"], files[f["name"]])
                continue
            w.add(f["name"], build_file(files[f["name"]], f, all_texts[(base, f["name"])],
                                       remap, default_names=(f["name"] == "zel_00.bmg")))
        out = os.path.join(OUT_DIR, base)
        raw = w.build()
        self_check(raw, spec)
        with open(out, "wb") as fh:
            fh.write(yaz0.encode(raw))
        print("  %-14s %d 文件 -> %d 字节" % (base, len(spec["files"]), os.path.getsize(out)))


main()
