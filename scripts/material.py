"""cn/ 素材读取层。

字库与消息归档由使用者自备（Yaz0 压缩的 RARC）。

  <font_source>/fontres.arc.yaz0   rubyres.arc.yaz0     字库（RARC 内是 BFN）
  <lang 的 source 目录>/bmgres.arc.yaz0 …                消息库（RARC 内是 BMG）

文件名就是部件名加 .yaz0，部件名与打包时写进包内的一致（fontres.arc / bmgres.arc）。
字库目录由 lang 段的 font_source 定（缺省 cn/font）；消息库取 lang 段的 source。
"""

import os
import struct
import sys

import paths
import yaz0

SUFFIX = ".yaz0"


def _load(dirpath, what):
    """[(部件名, 解 Yaz0 后的字节)]：目录下所有 <部件名>%s，按名字排序。""" % SUFFIX
    if not os.path.isdir(dirpath):
        sys.exit("缺 %s（%s）：把素材导出到这里" % (dirpath, what))
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
    """{部件名: RARC}：参照字库部件（fontres.arc / rubyres.arc）。"""
    return dict(_load(paths.font_source_dir(), "字库"))


def msg_arcs():
    """[(部件名, RARC)]：当前语言的源素材目录下的消息库部件（bmgres.arc / bmgres1.arc …）。"""
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
