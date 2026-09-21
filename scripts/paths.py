"""外部路径与默认配置的统一入口。

config.example.json 是完整默认值（路径字段写 <占位符>）；config.json 只写本机差异；
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
VARIANTS = (("open", "mod"), ("bmp", "mod_bmp"))
# 对外发布的变体；另一个变体（保留原字库位图）只在本机用 --variant 打
PUBLISHED_VARIANTS = ("open",)
PARTS_DIR = {"open": "sjis_parts", "bmp": "sjis_parts.bmp"}
# 字库部件文件名：不带槽位，同一个部件要写进各地区的 Font<region> 目录
FONT_PART_NAMES = ("fontres.arc", "rubyres.arc")


def parts_dir(variant):
    """变体的字库部件目录（work/ 下）。"""
    return os.path.join(WORK, PARTS_DIR[variant])


def font_parts(variant):
    """[(部件名, 路径)]：变体的两套字库部件。"""
    return [(n, os.path.join(parts_dir(variant), n)) for n in FONT_PART_NAMES]


def text_parts():
    """[(部件名, 路径)]：文本部件（两个变体共用，落在 open 的部件目录）。"""
    d = parts_dir("open")
    if not os.path.isdir(d):
        return []
    return [(n, os.path.join(d, n)) for n in sorted(os.listdir(d)) if n.startswith("bmgres")]

# 命令行参数 -> 配置字段
KEYS = {
    "--exe": "dusklight_exe",
    "--cn-font": "cn_font",
    "--glyph-source": "glyph_source",
    "--em": "em",
    "--mods-dir": "mods_dir",
    "--game-config": "game_config",
}

# 替换槽位：字库目录跟 region（Font<region>），消息目录跟 language（Msg<language>）
REGIONS = ("us", "eu", "jp")
LANGUAGES = ("uk", "us", "de", "fr", "sp", "it", "jp")
LANG_REGION = {"uk": "eu", "de": "eu", "fr": "eu", "sp": "eu", "it": "eu", "jp": "jp"}
# 元信息占位符 {region} / {language} 的展开（写给玩家看）
SLOT_NAMES = {
    "region": {"us": "United States", "eu": "Europe", "jp": "Japan"},
    "language": {"us": "English (US)", "uk": "English (UK)", "de": "German", "fr": "French",
                 "sp": "Spanish", "it": "Italian", "jp": "Japanese"},
}

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


def cli(name):
    """只看命令行的开关（--region / --variant 这类只在本次调用生效）。"""
    return _option(name)


def _need(name, what):
    value = option(name)
    if not value:
        sys.exit("%s：在 %s 里填 \"%s\"，或用 %s <路径> 指定" % (what, CONFIG, KEYS.get(name, name.lstrip("-")), name))
    return value


def mods_dir():
    return _need("--mods-dir", "需要游戏的 mod 目录（放 .dusk 的地方）")


def game_config():
    return _need("--game-config", "需要游戏 config.json 的路径")


def dusklight_exe():
    return _need("--exe", "需要 dusklight.exe 路径")


def discs():
    """[(region, language)]：config 的 discs，逐个校验。"""
    raw = config_value("discs")
    if not isinstance(raw, list) or not raw:
        sys.exit("%s 里缺 discs（每个盘一项 {region, language}）" % CONFIG)
    out = []
    for item in raw:
        region = str((item or {}).get("region") or "").lower()
        language = str((item or {}).get("language") or "").lower()
        if region not in REGIONS:
            sys.exit("discs 里的 region 无效：%r（可选 %s）" % (region, " / ".join(REGIONS)))
        if language not in LANGUAGES:
            sys.exit("discs 里的 language 无效：%r（可选 %s）" % (language, " / ".join(LANGUAGES)))
        expect = LANG_REGION.get(language)
        if expect and expect != region:
            print("警告：language=%s 通常出现在 %s 版盘，region=%s 可能没有该消息槽"
                  % (language, expect, region), file=sys.stderr)
        out.append((region, language))
    return out


def pick_disc(want, flag="--region"):
    """挑一个地区：want 为空时只在配置里恰好一个地区时可用。"""
    all_discs = discs()
    if not want:
        if len(all_discs) != 1:
            sys.exit("配置里有 %d 个地区，用 %s 指定（%s）"
                     % (len(all_discs), flag, " / ".join(r for r, _ in all_discs)))
        return all_discs[0]
    for disc in all_discs:
        if disc[0] == want:
            return disc
    sys.exit("配置的 discs 里没有地区 %s（%s）" % (want, " / ".join(r for r, _ in all_discs)))


def font_dir(region):
    """字库目录（随光盘区域）：Fontus / Fonteu / Fontjp。"""
    return "Font" + region


def msg_dir(language):
    """消息目录（随语言）：Msgus / Msgfr / ...。"""
    return "Msg" + language


def expand(text, region, language):
    """展开显示文本里的 {region} / {language} / {repo}（地区写成 United States 这类全称）。"""
    repo = str(config_value("repo") or "")
    if "{repo}" in text and not repo:
        print("警告：用了 {repo} 占位符，但配置里没写 repo", file=sys.stderr)
    return (text.replace("{region}", SLOT_NAMES["region"][region])
                .replace("{language}", SLOT_NAMES["language"][language])
                .replace("{repo}", repo))


def expand_id(text, region, language):
    """展开 id 里的 {region} / {language}（写成 us / eu / jp 这类短名，要进 mod id 与文件名）。"""
    return text.replace("{region}", region).replace("{language}", language)


def escape_mod_id(mod_id):
    """mod id 按引擎规则转成配置键/文件名：'.' -> '_'，'_' -> '__'。"""
    return mod_id.replace("_", "__").replace(".", "_")


def out_dir():
    """成品包目录（config 的 out）。"""
    value = config_value("out")
    if not value:
        sys.exit("%s 里缺 out（成品包目录）" % CONFIG)
    return value if os.path.isabs(value) else os.path.join(ROOT, value)


def mod_meta(variant, region, language):
    """变体在某地区的元信息：config 的 mod / mod_bmp 段展开占位符。"""
    key = dict(VARIANTS)[variant]
    meta = config_value(key)
    if not isinstance(meta, dict) or not meta.get("id"):
        sys.exit("%s 里缺 %s 段（id/name/version/author/description）" % (CONFIG, key))
    out = dict(meta)
    out["id"] = expand_id(str(out["id"]), region, language)
    for field in ("name", "description"):
        if isinstance(out.get(field), str):
            out[field] = expand(out[field], region, language)
    return out


def package_path(variant, region, language):
    """成品包路径：out 目录 / <转义 id>.dusk（id 带地区，文件名自然带地区后缀）。"""
    return os.path.join(out_dir(), escape_mod_id(mod_meta(variant, region, language)["id"]) + ".dusk")
