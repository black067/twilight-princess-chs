"""外部路径与默认配置的统一入口。

config.example.json 是完整默认值（入库，路径字段写 <占位符>）；config.json 只写本机差异；
--xxx 命令行再覆盖。两者递归合并。
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
CONFIG_EXAMPLE = os.path.join(HERE, "config.example.json")

# 两个成品变体：(变体名, config 里的元信息段)。字库部件目录也在 work 下由这里定，
# 字库/打包/安装脚本共用，避免各写一份。
VARIANTS = (("open", "mod"), ("ique", "mod_ique"))
PARTS_DIR = {"open": "sjis_parts", "ique": "sjis_parts.ique"}


def parts_dir(variant):
    """变体的字库部件目录（work/ 下）。"""
    return os.path.join(WORK, PARTS_DIR[variant])

# 命令行参数 -> 配置字段
KEYS = {
    "--pak": "pak",
    "--pak-old": "pak_old",
    "--game-dir": "game_dir",
    "--exe": "dusklight_exe",
    "--cn-font": "cn_font",
    "--glyph-source": "glyph_source",
    "--em": "em",
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


def _load(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        sys.exit("读取 %s 失败：%s" % (path, exc))
    return doc if isinstance(doc, dict) else {}


def _overlay(base, over):
    """递归覆盖：两边都是 dict 的逐键合并，其余整体覆盖。"""
    out = dict(base)
    for key, value in over.items():
        if isinstance(out.get(key), dict) and isinstance(value, dict):
            out[key] = _overlay(out[key], value)
        else:
            out[key] = value
    return out


def _drop_placeholders(doc):
    """<说明> 占位符当成没配。"""
    out = {}
    for key, value in doc.items():
        if isinstance(value, dict):
            out[key] = _drop_placeholders(value)
        elif isinstance(value, str) and value.startswith("<") and value.endswith(">"):
            continue
        else:
            out[key] = value
    return out


def _config():
    global _cache
    if _cache is None:
        _cache = _overlay(_drop_placeholders(_load(CONFIG_EXAMPLE)),
                          _drop_placeholders(_load(CONFIG)))
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
