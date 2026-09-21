# 塞尔达传说：黄昏公主汉化 MOD

塞尔达传说：黄昏公主的汉化 mod，用于 [dusklight](https://github.com/TwilitRealm/dusklight)

> **本仓库只有脚本与文档**
> 官方素材（APK、pak、提取出的 `cn/text/` 与 `cn/font/`、打出来的 `.dusk` 成品包）**请自行准备**，用脚本从自备的正版 pak 获取

**现状**：**版独有的官方简体中文文本与中文字库已完整提取，并且全部游戏内文本的中文已在 dusklight 上跑通——
标题提示、存档界面、对话、菜单、栏位文字、电视设置页面都正常，主角名与马名正常，中文名字键盘可用（open 变体）。
工程细节见 [docs/技术备忘.md](docs/技术备忘.md)，逆向过程见 [docs/研究报告.md](docs/研究报告.md)。

## 仓库内容

| 路径 | 内容 |
| --- | --- |
| `scripts/` | 提取与移植管线（Python，只用标准库；外部路径见 `config.example.json`）。字库重渲染 `font_render.py` 走 Windows GDI+，**只支持 Windows** |
| `data/` | 入库的小数据：`name_keyboard.json` |
| `docs/` | 文档：技术备忘 / 管线复现 / 发布指南 / 研究报告（见下方「文档」） |
| `tools/` | 配套工具：`dusklight-download/` 拉 dusklight / dusk-cn 的 release、启盘镜像 |
| `cn-mod/` | 引擎侧探针（只当仪器用，正式修复走数据侧） |
| `cn/text/`、`cn/font/` | 官方素材，由脚本现产（不入库） |
| `dist/` | 打出来的 `.dusk` 成品包（开源字体版 / 官方字库版，不入库） |
| `work/` | 中间数据：`sjis_parts*` 部件、`fonts/` 开源字体、`keyboard_aliases.json`、诊断脚本与缓存（不入库） |

原始样本：新版 `The_Legend_of_Zelda_Twilight_Princess_**.**`，
差分对照的旧版 `**.**`；哈希与尺寸见研究报告第 1 节。

## 快速开始

```pwsh
# 0) 自备开源字体（open 变体重渲染用，不入库）
#    work/fonts/NotoSansCJKsc-Regular.otf  思源黑体 / Noto Sans CJK SC（OFL-1.1）
#    work/fonts/LXGWWenKai-Regular.ttf     霞鹜文楷（OFL-1.1）

# 1) 从自备正版 pak 导出官方素材到 cn/（不入库）
python scripts/export_cn_archive.py        # 文本 + 字库
python scripts/export_cn_text.py           # 标签感知的文本导出

# 2) 移植管线（可调项与完整命令见 docs/管线复现.md）
python scripts/extract_name_keyboard.py    # 键盘字表 → data/name_keyboard.json（已入库，会自动跳过）
python scripts/sjis_map.py                 # 码位映射 → work/sjis_map.json
python scripts/patch_sjis_font.py          # 字库：open（开源字体重渲染）+ ique（官方字库只重排）两个变体
python scripts/patch_sjis_text.py          # 消息重编码
python scripts/diag_pack.py                # 验收：未正常结束 0 条、缺字 0 次
python scripts/build_sjis_pack.py --check  # 先校验 mod.json 元数据
python scripts/build_sjis_pack.py          # 打包 → dist/<id>.dusk + dist/<id>_ique.dusk

# 3) 装进游戏（自动拷包 + 改 data/config.json 开关）
python scripts/install.py                  # --variant ique 装官方字库版；--list 只看现状
```

路径 / 槽位 / 字体 / 元信息都在 `scripts/config.example.json`（`region` / `language` 默认 `eu` / `fr`，即欧版法语槽）；
`scripts/config.json` 只写本机路径差异，两者递归合并、命令行 `--xxx` 再覆盖。

## 使用成品包

1. 取 [snnh/dusk-cn](https://github.com/snnh/dusk-cn)（dusklight 的中文增强分支）的 release 解压到游戏目录。
2. `python scripts/install.py` 装包（`--variant ique` 装官方字库版）；也可以手工把 `dist/<id>.dusk` 放进
   `<游戏目录>/data/mods/`，再把 `data/config.json` 里该包的 `mod.<id>.enabled` 置 `true`。
3. 游戏镜像需自备正版：本项目在 GameCube 欧版 + `game.language = 2`（法语槽）上验证。
4. 验证：标题提示、存档、对话、菜单、栏位文字应为简体中文，名字框默认名「林克 / 伊波娜」可正常显示；
   日志在 `%APPDATA%\TwilitRealm\Dusklight\logs\`。旧存档的名字是旧码位，会显示成错字——新建存档或重输一次名字。

两个变体覆盖同一批资源、只能装一个：`dist/yiga_zh_hans.dusk`（开源字体渲染）与 `dist/yiga_zh_hans_ique.dusk`
（保留官方字库位图）。中文名字键盘与键盘补全只对 open 变体成立；用上游 dusklight 时没有中文键盘（那是 dusk-cn 分支的功能）。

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/技术备忘.md](docs/技术备忘.md) | 素材清单、BMG / BFN 格式、引擎侧关键事实、移植路线（根因 + 修法）、名字与键盘、校验与排障工具 |
| [docs/管线复现.md](docs/管线复现.md) | 配置分层、完整命令与可调项、`install.py` 行为、常见坑 |
| [docs/发布指南.md](docs/发布指南.md) | 上传官方 mod 站的字段规则与手工项 |
| [docs/研究报告.md](docs/研究报告.md) | ** pak 的逆向研究报告 |

## 许可与免责

- **代码与文档**：MIT 许可，见 [LICENSE](LICENSE)。
- **不含游戏素材**：官方文本、字库、游戏数据及其派生成品包都不在仓库里；请自备正版
  《塞尔达传说：黄昏公主》（** ** **版）数据，用 `scripts/` 在本地导出。
  这些素材的版权归任天堂 / ** 等原权利人所有，不属于本仓库的许可范围。
- **开源字体**：open 变体的字形由思源黑体 / Noto Sans CJK SC 与霞鹜文楷（均 OFL-1.1）渲染，字体文件不入库、
  放 `work/fonts/` 自行获取；渲染出的位图随成品包分发，建议在站点页面注明所用字体与许可。
- **无关联**：本项目与任天堂、** 及其关联公司无关，未获其授权或认可；仅供学习与研究，使用者自行承担风险。
