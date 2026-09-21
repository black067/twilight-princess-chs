"""外部路径统一入口。

机器相关路径（pak、游戏目录、dusklight.exe）统一写在同目录的 config.json 里，
命令行参数可逐个覆盖；脚本本身只认仓库内相对路径。
config.json 的模板见 config.example.json
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, "work")
DATA = os.path.join(ROOT, "data")
CN = os.path.join(ROOT, "cn")
CONFIG = os.path.join(HERE, "config.json")

# 命令行参数 -> 配置字段
KEYS = {
    "--pak": "pak",
    "--pak-old": "pak_old",
    "--game-dir": "game_dir",
    "--exe": "dusklight_exe",
}

# 替换槽位：字库目录跟 region（Font<region>），消息目录跟 language（Msg<language>）
REGIONS = ("us", "eu", "jp")
LANGUAGES = ("uk", "us", "de", "fr", "sp", "it", "jp")
LANG_REGION = {"uk": "eu", "de": "eu", "fr": "eu", "sp": "eu", "it": "eu", "jp": "jp"}

_cache = None


def _option(name):
    for i, arg in enumerate(sys.argv):
        if arg == name:
            return sys.argv[i + 1]
        if arg.startswith(name + "="):
            return arg.split("=", 1)[1]
    return None


def _config():
    global _cache
    if _cache is None:
        _cache = {}
        if os.path.exists(CONFIG):
            try:
                with open(CONFIG, encoding="utf-8") as f:
                    _cache = json.load(f)
            except (OSError, ValueError) as exc:
                sys.exit("读取 %s 失败：%s" % (CONFIG, exc))
    return _cache


def config_value(key, default=None):
    value = _config().get(key)
    return default if value is None else value


def config_dir(key, default):
    """取配置里的目录：相对路径按仓库根解析。"""
    value = config_value(key) or default
    return value if os.path.isabs(value) else os.path.join(ROOT, value)


def option(name):
    """命令行 > 配置文件；两者都没有返回 None。"""
    value = _option(name)
    if value:
        return value
    return _config().get(KEYS.get(name, name.lstrip("-").replace("-", "_")))


def _need(name, what):
    value = option(name)
    if not value:
        sys.exit("%s：在 %s 里填 \"%s\"，或用 %s <路径> 指定" % (what, CONFIG, KEYS.get(name, name.lstrip("-")), name))
    return value


def pak():
    return _need("--pak", "需要** pak 路径")


def pak_old():
    return _need("--pak-old", "需要旧版样本 pak 路径")


def game_dir():
    return _need("--game-dir", "需要游戏目录")


def dusklight_exe():
    return _need("--exe", "需要 dusklight.exe 路径")


def slot():
    """(region, language)：字库目录跟 region，消息目录跟 language。"""
    region = str(config_value("region") or "eu").lower()
    language = str(config_value("language") or "fr").lower()
    if region not in REGIONS:
        sys.exit("config.json 的 region 无效：%s（可选 %s）" % (region, " / ".join(REGIONS)))
    if language not in LANGUAGES:
        sys.exit("config.json 的 language 无效：%s（可选 %s）" % (language, " / ".join(LANGUAGES)))
    expect = LANG_REGION.get(language)
    if expect and expect != region:
        print("警告：language=%s 通常出现在 %s 版盘，region=%s 可能没有该消息槽"
              % (language, expect, region), file=sys.stderr)
    return region, language


def font_dir():
    """字库目录（随光盘区域）：Fontus / Fonteu / Fontjp。"""
    return "Font" + slot()[0]


def msg_dir():
    """消息目录（随语言）：Msgus / Msgfr / ...。"""
    return "Msg" + slot()[1]


def escape_mod_id(mod_id):
    """mod id 按引擎规则转成配置键/文件名：'.' -> '_'，'_' -> '__'。"""
    return mod_id.replace("_", "__").replace(".", "_")


def mod_path():
    """成品包默认路径：out 目录 / <转义 id>.dusk。"""
    mod = config_value("mod")
    if not isinstance(mod, dict) or not mod.get("id"):
        sys.exit("%s 里缺 mod 元信息（id/name/version/author/description）" % CONFIG)
    return os.path.join(config_dir("out", os.path.join("work", "mods")),
                        escape_mod_id(mod["id"]) + ".dusk")
