# 塞尔达传说：黄昏公主汉化 MOD

塞尔达传说：黄昏公主的汉化 mod，用于 [dusklight](https://github.com/TwilitRealm/dusklight)

> **本仓库只有脚本与文档**
> 输入素材（`input/`）与产物（`dist/`、`work/`）请通过合法途径自行获取；输入格式见 [docs/管线复现.md](docs/管线复现.md)

**现状**：中文文本与中文字库已全部就位，全部游戏内文本的中文已在 dusklight 上跑通——
标题提示、存档界面、对话、菜单、栏位文字、电视设置页面都正常，主角名与马名正常，中文名字键盘可用。
文本、容器与字库都由仓库里的脚本从译文表与开源字体生成。
工程细节见 [docs/技术备忘.md](docs/技术备忘.md)。

## 目录

| 路径 | 内容 |
| --- | --- |
| `scripts/` | 移植与打包管线（Python，只用标准库；外部路径见 `config.example.json`）。字库重渲染 `font_render.py` 走 Windows GDI+，**只支持 Windows** |
| `data/` | 名字键盘字表、每语言的容器索引 `msg_index.<lang>.json`、文本资源形状表（`text_resources.json`） |
| `docs/` | 文档：技术备忘 / 管线复现 / 发布指南（见下方「文档」） |
| `tools/` | 配套工具：`dusklight-download/` 拉 dusklight / dusk-cn 的 release、启盘镜像 |
| `input/` | 素材输入（自备）：消息库、参照字库、译文表；根目录由 config 的 `input_dir` 定 |
| `assets/` | 上架素材：`icon.png`（299×299）、`banner.png`（1600×457）、`preview-*.png`；lang 段的 `mod.icon` / `mod.banner` 指向它们 |
| `dist/` | 打出来的 `.dusk` 成品包 |
| `work/` | 中间数据，**按语言分目录**（`work/<lang>/`）：`scratch_parts*/`、`sjis_parts*/` 部件与码位表；`work/fonts/` 是开源字体与标定对照图 |

## 快速开始

```pwsh
# 0) 输入（放哪由 config 定）：
#    开源字体：思源黑体 / Noto Sans CJK SC、霞鹜文楷（均 OFL-1.1）→ fonts.<字库>.file
#    游戏素材：两套字库归档 → font_source；各语言的 10 个消息库 → langs.<lang>.source

# 1) 索引与译文表（一次；之后改译文只动 input/texts.zh-Hans.csv 的译文列）
python scripts/msg_index.py                # 源归档 -> data/msg_index.zh-Hans.json
python scripts/export_texts.py             # 源归档 -> input/texts.zh-Hans.csv

# 2) 打包（容器与字库都从零生成；另一条就地改写路线见 docs/管线复现.md）
python scripts/build_bmg.py                # 消息容器（读译文表，顺带写 work/zh-Hans/code_map.json）
python scripts/build_bfn.py                # 两套字库（读同一份码位表）→ work/zh-Hans/scratch_parts/
Copy-Item work\zh-Hans\scratch_parts\*.arc work\zh-Hans\sjis_parts\ -Force   # 部件归位到打包目录
python scripts/verify_texts.py             # 部件 vs 译文表逐格比：不一致 0 格
python scripts/diag_pack.py                # 验收：未正常结束 0 条、缺字 0 次
python scripts/build_sjis_pack.py --check  # 先校验 mod.json 元数据
python scripts/build_sjis_pack.py          # 打包 → dist/yiga_zh_hans_<region>.dusk（3 个地区）

# 3) 装进游戏（拷包 + 改配置开关）
python scripts/install.py --region us      # --list 只看现状
```

一次作业由一个 `lang` 段描述（源素材目录 `source`、列名 `draft_col`/`locale_col`、槽位 `discs`、
元信息 `mod`/`mod_origin`）；上面这些命令都可用 `--lang <语言>` 换段（缺省 `default_lang`），
中间产物按语言分目录。已有的段见 `scripts/config.example.json` 的 `langs`。

路径 / 地区 / 字体 / 元信息都在 `scripts/config.example.json`：`input_dir` 指本地素材根（缺省 `input/`，
`font_source` 与各语言 `source` 的默认位置都从它派生），`discs` 一个盘一项（`region` = 字库目录
`Font<region>`，`language` = 消息目录 `Msg<language>`），默认美版 `us`/`us`、欧版 `eu`/`fr`、日版 `jp`/`jp`；
`scripts/config.json` 只写本机路径差异，两者递归合并、命令行 `--xxx` 再覆盖。

## 使用成品包

1. 取 [snnh/dusk-cn](https://github.com/snnh/dusk-cn)（dusklight 的中文增强分支）的 release 解压到游戏目录。
2. `python scripts/install.py --region <us|eu|jp>` 装包（`--lang` 选语言，缺省中文）；也可以手工把
   `dist/<id>.dusk` 放进游戏的 mod 目录，再把该包在配置里的 `mod.<id>.enabled` 置 `true`。
   mod 目录与配置路径由 `config.json` 的 `mods_dir` / `game_config` 指定（dusklight 2.x 是 exe 同级的
   `mods/` 与数据目录下的 `config.json`，dusk-cn 是 `<游戏目录>/data/` 下的那两个）。
3. 三个地区的盘各出一份包（美版 `Fontus`/`Msgus`、欧版法语槽 `Fonteu`/`Msgfr`、日版 `Fontjp`/`Msgjp`）；
   本项目在 GameCube 欧版 + `game.language = 2`（法语槽）上验证。
4. 验证：标题提示、存档、对话、菜单、栏位文字应为简体中文，名字框默认名「林克 / 伊波娜」可正常显示；
   日志在 `%APPDATA%\TwilitRealm\Dusklight\logs\`。旧存档的名字是旧码位，会显示成错字——新建存档或重输一次名字。

每个地区一个包（`dist/yiga_zh_hans_<region>.dusk`），换地区装新的会自动清掉旧的。
中文名字键盘与键盘补全只对开源字体包成立；用上游 dusklight 时没有中文键盘（那是 dusk-cn 分支的功能）。

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/技术备忘.md](docs/技术备忘.md) | 素材清单、容器格式、名字与键盘、校验与排障工具 |
| [docs/管线复现.md](docs/管线复现.md) | 配置分层、完整命令与可调项、`install.py` 行为、常见坑 |
| [docs/发布指南.md](docs/发布指南.md) | 上传 Dusklight mod 站的字段规则与手工项 |

## 许可与免责

- **代码与文档**：MIT 许可，见 [LICENSE](LICENSE)。
- **不含游戏素材**：文本、字库、游戏数据及其派生成品包都不在仓库里；版权归各原权利人所有，
  不属于本仓库的许可范围。
- **开源字体**：字形由思源黑体 / Noto Sans CJK SC 与霞鹜文楷（均 OFL-1.1）渲染，字体文件需自行下载、
  放 `work/fonts/`；渲染出的位图随成品包分发，建议在站点页面注明所用字体与许可。
- **无关联**：本项目与任天堂及其关联公司无关，未获其授权或认可；仅供学习与研究，使用者自行承担风险。
