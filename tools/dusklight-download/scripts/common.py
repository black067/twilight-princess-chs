#!/usr/bin/env python3
"""dusklight-download 的公共逻辑：配置与路径解析。

脚本只认工具目录内的相对路径；输出目录与下载来源一律由 config.json 给出，
命令行参数可覆盖。只依赖标准库，Windows / macOS / Linux 通用。
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_NAME = "config.json"


def config_path(override=None):
    return Path(override) if override else ROOT / CONFIG_NAME


def load_config(override=None):
    """读配置；文件不存在返回 None。"""
    path = config_path(override)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def dist_root(cfg, override=None):
    """输出根目录：命令行 > 配置 > 默认 dist；相对路径按工具目录解析。"""
    if not isinstance(cfg, dict):
        cfg = {}
    value = override or cfg.get("dist") or "dist"
    path = Path(value)
    return path if path.is_absolute() else ROOT / path
