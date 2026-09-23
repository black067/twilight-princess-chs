"""外部路径与配置的统一入口

`config.default.json` 是固有打包参数，`config.local.json` 只写本机差异，`--xxx` 命令行再覆盖。
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, "work")
DATA = os.path.join(ROOT, "data")
CONFIG_LOCAL = os.path.join(HERE, "config.local.json")
CONFIG_DEFAULT = os.path.join(HERE, "config.default.json")

# 变体名（别的脚本读常量，别写字面量）：open = 容器与字库从零生成；
# origin = 改现成素材，保留原字库位图。
OPEN_VARIANT = "open"
ORIGIN_VARIANT = "origin"
# 两个成品变体：(变体名, config 里的元信息段)
VARIANTS = ((OPEN_VARIANT, "mod"), (ORIGIN_VARIANT, "mod_origin"))
# 不带 --variant 时打的变体（其余变体要在命令行显式指定）
PUBLISHED_VARIANTS = (OPEN_VARIANT,)
# 资源目录（字库 + 文本）也在 work 下由这里定：一个变体一个目录，互不覆盖
PARTS_DIR = {OPEN_VARIANT: "parts.open", ORIGIN_VARIANT: "parts.origin"}
# 字库资源文件名：不带地区，同一个资源要写进各地区的 Font<region> 目录
FONT_PART_NAMES = ("fontres.arc", "rubyres.arc")


def parts_dir(variant):
    """变体的资源目录（work/<lang>/ 下）：各出各的字库与文本，不互相覆盖。"""
    return os.path.join(work_dir(), PARTS_DIR[variant])


def font_parts(variant):
    """[(资源名, 路径)]：变体的两套字库资源。"""
    return [(n, os.path.join(parts_dir(variant), n)) for n in FONT_PART_NAMES]


def text_parts(variant):
    """[(资源名, 路径)]：变体自己那份文本资源（码位方案与它的字库配套）。"""
    d = parts_dir(variant)
    if not os.path.isdir(d):
        return []
    return [(n, os.path.join(d, n)) for n in sorted(os.listdir(d)) if n.startswith("bmgres")]

# 字库与文本必须同一码位方案，所以中间产物目录与键盘期望表都按方案分开
CODE_SPACES = ("own", "sjis")
DEFAULT_CODE_SPACE = "own"
SCRATCH_DIR = {"own": "parts.open.own", "sjis": "parts.open.sjis"}
KB_JSON = {"own": "keyboard_aliases.json", "sjis": "keyboard_aliases.sjis.json"}


def scratch_dir(space=DEFAULT_CODE_SPACE):
    return os.path.join(work_dir(), SCRATCH_DIR[space])


def kb_json(space=DEFAULT_CODE_SPACE):
    return os.path.join(work_dir(), KB_JSON[space])


def code_map_json():
    return os.path.join(work_dir(), "code_map.json")


def sjis_map_json():
    return os.path.join(work_dir(), "sjis_map.json")


def msg_index_json():
    return os.path.join(DATA, "msg_index.%s.json" % lang())


def font_source_dir():
    """参照字库目录（本地化方案的 font_source，缺省 <input_dir>/font）。"""
    value = lang_value("font_source")
    if not value:
        return os.path.join(input_dir(), "font")
    return value if os.path.isabs(value) else os.path.join(ROOT, value)


# 命令行参数 -> 配置字段
KEYS = {
    "--exe": "dusklight_exe",
    "--em": "em",
    "--mods-dir": "mods_dir",
    "--game-config": "game_config",
}

# 替换目录：字库目录跟 region（Font<region>），消息目录跟 language（Msg<language>）
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
        _cache = _overlay(_drop_placeholders(_load(CONFIG_DEFAULT)),
                          _drop_placeholders(_load(CONFIG_LOCAL)))
    return _cache


def config_value(key, default=None):
    value = _config().get(key)
    return default if value is None else value


def config_dir(key, default):
    """取配置里的目录：相对路径按仓库根解析。"""
    value = config_value(key) or default
    return value if os.path.isabs(value) else os.path.join(ROOT, value)


def _langs():
    langs = config_value("langs")
    if not isinstance(langs, dict) or not langs:
        sys.exit("%s 里缺 langs（每个语言一段：source / draft_col / locale_col / discs / mod）"
                 % CONFIG_DEFAULT)
    return langs


def lang():
    """本次要处理的语言（--lang，缺省 default_lang；配置里只有一个时就用它）。"""
    name = cli("--lang") or config_value("default_lang")
    langs = _langs()
    if not name:
        if len(langs) == 1:
            return next(iter(langs))
        sys.exit("配置里有 %d 个语言，用 --lang 指定（%s）"
                 % (len(langs), " / ".join(sorted(langs))))
    if name not in langs:
        sys.exit("--lang %s 不在配置的 langs 里（%s）" % (name, " / ".join(sorted(langs))))
    return name


def lang_config():
    """当前语言的全量配置：本地化方案递归覆盖顶层（顶层 fonts 是默认值，本地化方案可只覆盖要改的）。"""
    return _overlay(_config(), _langs()[lang()])


def lang_value(key, default=None):
    value = lang_config().get(key)
    return default if value is None else value


def work_dir():
    """当前语言的中间产物根目录（work/<lang>/）。"""
    return os.path.join(WORK, lang())


def source_dir():
    """本地化方案的 source：该语言要导出的解包素材目录。"""
    value = lang_value("source")
    if not value:
        sys.exit("%s 的 langs.%s 里缺少 source (解包素材目录)" % (CONFIG_DEFAULT, lang()))
    return value if os.path.isabs(value) else os.path.join(ROOT, value)


def input_dir():
    """本地素材根（顶层 input_dir，缺省 input）：消息库、参照字库、译文表都在它下面。"""
    value = config_value("input_dir") or "input"
    return value if os.path.isabs(value) else os.path.join(ROOT, value)


def texts_file():
    """译文表：<input_dir>/texts.<lang>.csv（与素材放在一起）。"""
    return os.path.join(input_dir(), "texts.%s.csv" % lang())


def _col(key):
    value = lang_value(key)
    if not value:
        sys.exit("%s 的 langs.%s 里缺少 %s (列名)" % (CONFIG_DEFAULT, lang(), key))
    return value


def draft_col():
    """底稿列（导出时从素材读出来的原文）。"""
    return _col("draft_col")


def locale_col():
    """译文列（打包只读它）。"""
    return _col("locale_col")


def option(name):
    """命令行 > 配置文件；两者都没有返回 None。"""
    value = _option(name)
    if value:
        return value
    return _config().get(KEYS.get(name, name.lstrip("-").replace("-", "_")))


def cli(name):
    """只看命令行的开关（--region / --variant 这类只在本次调用生效）。"""
    return _option(name)


def code_space():
    space = cli("--code-space") or DEFAULT_CODE_SPACE
    if space not in CODE_SPACES:
        sys.exit("--code-space 只支持 %s（现在 %r）" % (" / ".join(CODE_SPACES), space))
    return space


def _need(name, what):
    value = option(name)
    if not value:
        sys.exit("%s：在 %s 里填 \"%s\"，或用 %s <路径> 指定" % (what, CONFIG_LOCAL, KEYS.get(name, name.lstrip("-")), name))
    return value


def mods_dir():
    return _need("--mods-dir", "需要游戏的 mod 目录（放 .dusk 的地方）")


def game_config():
    return _need("--game-config", "需要游戏 config.json 的路径")


def dusklight_exe():
    return _need("--exe", "需要 dusklight.exe 路径")


def discs():
    """[(region, language)]：当前语言的 discs，逐个校验。"""
    raw = lang_value("discs")
    if not isinstance(raw, list) or not raw:
        sys.exit("%s 的 langs.%s 里缺 discs (每个盘一项 {region, language})" % (CONFIG_DEFAULT, lang()))
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
            print("警告：language=%s 通常出现在 %s 版盘，region=%s 可能没有该消息目录"
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
    """成品包目录（out：顶层默认，本地化方案可覆盖）。"""
    value = lang_value("out")
    if not value:
        sys.exit("%s 里缺少 out (成品包目录)" % CONFIG_DEFAULT)
    return value if os.path.isabs(value) else os.path.join(ROOT, value)


def mod_meta(variant, region, language):
    """变体在某地区的元信息：展开当前语言的它那段（VARIANTS 的第二项）的占位符。"""
    key = dict(VARIANTS)[variant]
    meta = lang_value(key)
    if not isinstance(meta, dict) or not meta.get("id"):
        sys.exit("%s 的 langs.%s 里缺少 %s 段 (需要: id/name/version/author/description)"
                 % (CONFIG_DEFAULT, lang(), key))
    out = dict(meta)
    out["id"] = expand_id(str(out["id"]), region, language)
    for field in ("name", "description"):
        if isinstance(out.get(field), str):
            out[field] = expand(out[field], region, language)
    return out


def package_path(variant, region, language):
    """成品包路径：out 目录 / <转义 id>.dusk（id 带地区，文件名自然带地区后缀）。"""
    return os.path.join(out_dir(), escape_mod_id(mod_meta(variant, region, language)["id"]) + ".dusk")
