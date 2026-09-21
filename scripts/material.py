"""cn/ 素材读取层。

字库与消息归档由使用者自备，放在 cn/ 下（Yaz0 压缩的 RARC）。

  cn/font/fontres.arc.yaz0   cn/font/rubyres.arc.yaz0     字库（RARC 内是 BFN）
  cn/msg/bmgres.arc.yaz0 …   cn/msg/bmgres99.arc.yaz0     消息库（RARC 内是 BMG）

文件名就是部件名加 .yaz0，部件名与打包时写进包内的一致（fontres.arc / bmgres.arc）。
"""

import os
import sys

import paths
import yaz0

FONT_DIR = os.path.join(paths.CN, "font")
MSG_DIR = os.path.join(paths.CN, "msg")
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
    """{部件名: RARC}：字库部件（fontres.arc / rubyres.arc）。"""
    return dict(_load(FONT_DIR, "字库"))


def msg_arcs():
    """[(部件名, RARC)]：消息库部件（bmgres.arc / bmgres1.arc …）。"""
    return _load(MSG_DIR, "消息库")
