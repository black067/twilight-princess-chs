"""RARC 归档写入：按 JKRArchive 的磁盘格式拼单节点归档。

格式（`libs/JSystem/src/JKernel/JKRMemArchive.cpp` + `JKRArchive.h`）：
- 头 0x20：`RARC` / 文件长度 / header_length(0x20) / file_data_offset / file_data_length / 三个未知字段
- 信息块在 header_length（0x20）处：节点数 / 节点表偏移 / 文件数 / 文件表偏移 /
  字符串表长度 / 字符串表偏移 / next_free_file_id(u16) / sync(u8)
- 节点 0x10：type('ROOT') / 名字偏移 / 名字哈希(u16) / 条目数 / 首个条目下标
- 文件项 0x14：file_id(u16) / 名字哈希(u16) / flags<<24 | 名字偏移 / data_offset / data_size / 4 字节 data 指针字段（主机端用，写 0）
- 节点/文件/字符串表的偏移都相对**信息块起点**（= header_length）；
  data_offset 相对 `header_length + file_data_offset`，每条数据按 0x20 对齐

名字哈希（`JKRArchive::CArcName::store`）：`h = (tolower(ch) + h * 3) & 0xFFFF`，初值 0。
引擎按名字取文件（`JKRGetTypeResource('ROOT', "zel_00.bmg", arc)`）时先比哈希再 strcmp，
所以哈希必须算对。
"""

import struct

ALIGN = 0x20


def name_hash(name):
    h = 0
    for ch in name.lower().encode():
        h = (ch + h * 3) & 0xFFFF
    return h


def align_up(n, a=ALIGN):
    return (n + a - 1) // a * a


class Writer:
    """单 ROOT 节点的 RARC（归档内是平铺的文件，和原归档一样）。"""

    def __init__(self, root_name, dot_entries=True):
        self.root_name = root_name
        # 目录占位项 "." / ".."：原归档里就是两个 file 项（file_id=0xFFFF、flags=0x02、size=16）
        self.dot_entries = dot_entries
        self.files = []

    def add(self, name, data):
        self.files.append((name, data))

    def build(self):
        strings = bytearray(b".\x00..\x00")
        offsets = {".": 0, "..": 2}

        def intern(text):
            if text not in offsets:
                offsets[text] = len(strings)
                strings.extend(text.encode() + b"\x00")
            return offsets[text]

        root_off = intern(self.root_name)
        entries = []
        for i, (n, _) in enumerate(self.files):
            entries.append((i, name_hash(n), 0x11, intern(n), n))
        if self.dot_entries:
            for dot in (".", ".."):
                entries.append((0xFFFF, name_hash(dot), 0x02, intern(dot), dot))

        info = 0x20
        node_tab_off = 0x20                                   # 信息块头自身占 0x20
        file_tab_off = align_up(node_tab_off + 0x10)          # 单节点，按下个 0x20 对齐
        str_tab_off = align_up(file_tab_off + len(entries) * 0x14)
        str_len = align_up(len(strings))
        data_off = str_tab_off + str_len
        data_start = info + data_off

        blob = bytearray()
        if self.dot_entries:
            blob.extend(b"\x00" * 16)
        positions = {}
        for n, data in self.files:
            while len(blob) % ALIGN:
                blob.append(0)
            positions[n] = len(blob)
            blob.extend(data)

        total = data_start + len(blob)
        out = bytearray()
        out += struct.pack(">4sIIIIIII", b"RARC", total, info, data_off, len(blob), 0, 0, 0)
        out += struct.pack(">IIIIII", 1, node_tab_off, len(entries), file_tab_off,
                           str_len, str_tab_off)
        out += struct.pack(">HB", len(entries), 1)
        out += b"\x00" * (info + node_tab_off - len(out))     # 信息块头补满 0x20
        out += struct.pack(">IIHHI", int.from_bytes(b"ROOT", "big"), root_off,
                           name_hash(self.root_name), len(entries), 0)
        out += b"\x00" * (info + file_tab_off - len(out))     # 节点表补空
        sizes = dict(self.files)
        for fid, nh, flags, noff, path in entries:
            if path in positions:
                doff, dsize = positions[path], len(sizes[path])
            else:
                doff, dsize = 0, 16
            # 磁盘上每条 0x14 字节：末 4 字节是主机端的 data 指针字段（这里写 0）
            out += struct.pack(">HHIII", fid, nh, (flags << 24) | noff, doff, dsize) + b"\x00" * 4
        out += b"\x00" * (info + str_tab_off - len(out))      # 文件表补空
        out += strings
        out += b"\x00" * (str_len - len(strings))
        assert len(out) == data_start, (len(out), hex(data_start))
        out += blob
        assert len(out) == total, (len(out), total)
        return bytes(out)
