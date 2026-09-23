"""素材读取层：读 `<input_dir>/` 下 Yaz0 压缩的 RARC（字库目录按本地化方案的 `font_source`，消息库按 `source`）。
"""

import os
import struct
import sys

import paths
import yaz0

SUFFIX = ".yaz0"


def _load(dirpath, what):
    """[(资源名, 解 Yaz0 后的字节)]：目录下所有 <资源名>%s，按名字排序。""" % SUFFIX
    if not os.path.isdir(dirpath):
        sys.exit("缺 %s（%s）：把素材放到这里" % (dirpath, what))
    out = []
    for name in sorted(os.listdir(dirpath)):
        if not name.endswith(SUFFIX):
            continue
        with open(os.path.join(dirpath, name), "rb") as f:
            out.append((name[: -len(SUFFIX)], yaz0.decompress(f.read())))
    if not out:
        sys.exit("%s 下没有 *%s（%s）" % (dirpath, SUFFIX, what))
    return out


def font_arcs():
    """{资源名: RARC}：参照字库资源（fontres.arc / rubyres.arc）。"""
    return dict(_load(paths.font_source_dir(), "字库"))


def msg_arcs():
    """[(资源名, RARC)]：当前语言的源素材目录下的消息库资源（bmgres.arc / bmgres1.arc …）。"""
    return _load(paths.source_dir(), "消息库")


def rarc_files(arc):
    """{归档内文件名: 数据}。信息块在 header_length 处，文件项占 0x14 字节。"""
    hdr = struct.unpack_from(">I", arc, 8)[0]
    _, _, nfiles, fileoff, stlen, stoff = struct.unpack_from(">IIIIII", arc, hdr)
    strtab = arc[hdr + stoff : hdr + stoff + stlen]
    data = hdr + struct.unpack_from(">I", arc, 0x0C)[0]
    out = {}
    for i in range(nfiles):
        o = hdr + fileoff + i * 0x14
        fid, nh, tfno, doff, dsize = struct.unpack_from(">HHIII", arc, o)
        if tfno >> 24 != 0x11:
            continue
        noff = tfno & 0xFFFFFF
        name = strtab[noff : strtab.index(b"\x00", noff)].decode()
        out[name] = arc[data + doff : data + doff + dsize]
    return out
