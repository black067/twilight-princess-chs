# 塞尔达传说：黄昏公主汉化 MOD

塞尔达传说：黄昏公主的汉化 mod，用于 [dusklight](https://github.com/TwilitRealm/dusklight)

> **本仓库只有脚本与文档**
> 输入素材（`cn/`）与产物（`dist/`、`work/`）请通过合法途径自行获取；输入格式见 [docs/管线复现.md](docs/管线复现.md)

**现状**：中文文本与中文字库已全部就位，全部游戏内文本的中文已在 dusklight 上跑通——
标题提示、存档界面、对话、菜单、栏位文字、电视设置页面都正常，主角名与马名正常，中文名字键盘可用。
文本、容器与字库都由仓库里的脚本从译文表与开源字体生成。
工程细节见 [docs/技术备忘.md](docs/技术备忘.md)。

## 目录

| 路径 | 内容 |
| --- | --- |
| `scripts/` | 移植与打包管线（Python，只用标准库；外部路径见 `config.example.json`）。字库重渲染 `font_render.py` 走 Windows GDI+，**只支持 Windows** |
| `data/` | 名字键盘字表、消息索引表（`msg_index.json`）、文本资源形状表（`text_resources.json`） |
| `docs/` | 文档：技术备忘 / 管线复现 / 发布指南（见下方「文档」） |
| `tools/` | 配套工具：`dusklight-download/` 拉 dusklight / dusk-cn 的 release、启盘镜像 |
| `cn-mod/` | 引擎侧探针（只当仪器用，正式修复走数据侧） |
| `cn/` | 素材输入（自备）：`msg/` `font/` 是管线要读的原始归档，`texts.csv` 是译文表，`text/` 供人读 |
| `dist/` | 打出来的 `.dusk` 成品包 |
| `work/` | 中间数据：`sjis_parts*/` 部件、`fonts/` 开源字体、`keyboard_aliases.json`、诊断脚本与缓存 |

## 快速开始

```pwsh
# 0) 输入：开源字体与 cn/ 素材
#    work/fonts/NotoSansCJKsc-Regular.otf  思源黑体 / Noto Sans CJK SC（OFL-1.1）
#    work/fonts/LXGWWenKai-Regular.ttf     霞鹜文楷（OFL-1.1）
#    cn/font/fontres.arc.yaz0  cn/font/rubyres.arc.yaz0  cn/msg/bmgres*.arc.yaz0

# 1) 译文表（一次；之后改译文只动 cn/texts.csv 的 zh-Hans 列）
python scripts/export_texts.py             # cn/msg/ → cn/texts.csv

# 2) 打包（容器与字库都从零生成；另一条就地改写路线见 docs/管线复现.md）
python scripts/build_bmg.py                # 消息容器（读 texts.csv，顺带写 work/code_map.json）
python scripts/build_bfn.py                # 两套字库（读同一份码位表）→ work/scratch_parts/
Copy-Item work\scratch_parts\*.arc work\sjis_parts\ -Force   # 部件归位到打包目录
python scripts/verify_texts.py             # 部件 vs texts.csv 逐格比：不一致 0 格
python scripts/diag_pack.py                # 验收：未正常结束 0 条、缺字 0 次
python scripts/build_sjis_pack.py --check  # 先校验 mod.json 元数据
python scripts/build_sjis_pack.py          # 打包 → dist/yiga_zh_hans_<region>.dusk（3 个地区）

# 3) 装进游戏（拷包 + 改配置开关）
python scripts/install.py --region us      # --list 只看现状
```

路径 / 地区 / 字体 / 元信息都在 `scripts/config.example.json`：`discs` 一个盘一项（`region` = 字库目录
`Font<region>`，`language` = 消息目录 `Msg<language>`），默认美版 `us`/`us`、欧版 `eu`/`fr`、日版 `jp`/`jp`；
`scripts/config.json` 只写本机路径差异，两者递归合并、命令行 `--xxx` 再覆盖。

## 使用成品包

1. 取 [snnh/dusk-cn](https://github.com/snnh/dusk-cn)（dusklight 的中文增强分支）的 release 解压到游戏目录。
2. `python scripts/install.py --region <us|eu|jp>` 装包；也可以手工把
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
