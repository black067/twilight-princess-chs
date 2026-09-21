"""外部路径统一入口。

脚本本身只认仓库内相对路径；pak、游戏目录、dusklight.exe 这些机器相关路径
一律由命令行参数或环境变量给出。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, "work")
DATA = os.path.join(ROOT, "data")
CN = os.path.join(ROOT, "cn")


def _option(name):
    for i, arg in enumerate(sys.argv):
        if arg == name:
            return sys.argv[i + 1]
        if arg.startswith(name + "="):
            return arg.split("=", 1)[1]
    return None


def option(name, env):
    return _option(name) or os.environ.get(env)


def _need(name, env, what):
    value = option(name, env)
    if not value:
        sys.exit("%s：用 %s <路径> 指定，或设置环境变量 %s" % (what, name, env))
    return value


def pak():
    return _need("--pak", "TP_PAK", "需要** pak 路径")


def pak_old():
    return _need("--pak-old", "TP_PAK_OLD", "需要旧版样本 pak 路径")


def game_dir():
    return _need("--game-dir", "TP_GAME_DIR", "需要 dusk-cn 游戏目录")


def dusklight_exe():
    return _need("--exe", "TP_DUSKLIGHT_EXE", "需要 dusklight.exe 路径")
