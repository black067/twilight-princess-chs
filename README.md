# 塞尔达传说：黄昏公主汉化 MOD

塞尔达传说：黄昏公主的汉化 mod，用于 [dusklight](https://github.com/TwilitRealm/dusklight)

> **本仓库只有脚本与文档**
> 官方素材（APK、pak、提取出的 `cn/text/` 与 `cn/font/`、打出来的 `.dusk` 成品包）**请自行准备**，用脚本从自备的正版 pak 获取

**现状**：**版独有的官方简体中文文本与中文字库已完整提取，并且全部游戏内文本的中文已在 dusklight 上跑通——
标题提示、存档界面、对话、菜单、栏位文字、电视设置页面都正常，主角名与马名正常，名字输入键盘可用。
做法全程纯数据、不改引擎，细节见[研究报告](docs/研究报告.md)与下文。

## 仓库内容

| 路径 | 内容 |
| --- | --- |
| `scripts/` | 提取与移植管线（Python，只用标准库；外部路径见 `config.example.json`） |
| `data/` | 入库的小数据：`name_keyboard.json` |
| `docs/` | 逆向研究报告 |
| `cn-mod/` | 引擎侧探针（只当仪器用，正式修复走数据侧） |
| `cn/text/`、`cn/font/` | 官方素材，由脚本现产 |
| `dist/` | 打出来的 `.dusk` 成品包（开源字体版 / 官方字库版） |
| `work/` | 中间数据：`sjis_parts*` 字库与文本部件、`fonts/` 开源字体、诊断脚本与缓存 |

原始样本：新版 `The_Legend_of_Zelda_Twilight_Princess_**.**`，
差分对照的旧版 `**.**`；哈希与尺寸见研究报告第 1 节。

## 复现

配置分两层：`scripts/config.example.json` 是完整默认值（入库、机器无关，路径字段写成 `<占位符>`），
`scripts/config.json` 只写本机差异（四个路径字段，不入库）；两者递归合并，命令行 `--xxx` 再覆盖。
替换槽位、字体、mod 元信息都在 `config.example.json` 里：`region`（字库目录 `Font<region>`，us/eu/jp）与
`language`（消息目录 `Msg<language>`，uk/us/de/fr/sp/it/jp）默认 `eu`/`fr`（欧版法语槽）；
字体按字库分开配 `fonts.fontres` / `fonts.rubyres`（各 `file`/`em`/`gamma`）——游戏里本来就是两套字库。
两个变体各有自己完整的一段元信息：`mod`（开源字体版）与 `mod_ique`（官方字库版，其 id 自带 `.ique`）——
id/name/description 各写各的；文件名现为 `dist/yiga_zh_hans.dusk`
与 `dist/yiga_zh_hans_ique.dusk`。

```pwsh
# 1) 读 pak
python scripts/extract_index.py <pak> work/index_new.bin          # 解密索引
python scripts/list_index.py   work/index_new.bin Msgcn Fontcn    # 按目录/关键字找条目
python scripts/extract_entry.py new 3                            # 取前 3 个条目看载荷
python scripts/**.py                                          # ** 实现自测

# 2) 导出官方素材到 cn/（不入库）
python scripts/export_cn_archive.py        # 文本 + 字库
python scripts/export_cn_text.py           # 标签感知的文本导出
python scripts/check_cn_coverage.py        # 文本码位 vs 字库覆盖核对

# 3) 移植管线，产出配置 out 目录下的两个成品包（dist/<id>.dusk 与 dist/<id>_ique.dusk）
python scripts/extract_name_keyboard.py    # 键盘字表 → data/name_keyboard.json（已随仓库提供，会自动跳过）
python scripts/sjis_map.py                 # 码位映射 → work/sjis_map.json
python scripts/patch_sjis_font.py          # 字库：一次产出开源字体（重渲染）与官方字库（只重排）两个变体
python scripts/patch_sjis_text.py          # 消息重编码（含默认名的单字节码位）
python scripts/diag_pack.py                # 验收，判据见「校验」
python scripts/build_sjis_pack.py          # 打包：dist/<id>.dusk + dist/<id>_ique.dusk（不安装）
python scripts/install.py                  # 安装：拷包 + 开关（--variant ique 装官方字库版，--list 只看现状）
```

## 环境与使用

运行环境是 [dusklight](https://github.com/TwilitRealm/dusklight)（黄昏公主的 PC 重实现），
本项目在 [snnh/dusk-cn](https://github.com/snnh/dusk-cn)（其中文增强分支，release v2.0.0）上验证。
游戏镜像需自备正版：本项目在 GameCube 欧版上验证，`game.language = 2` 即它的法语槽；换 dump/槽位见「复现」里的 `region`/`language`。

1. 取 dusk-cn 的 release 解压到游戏目录（便携模式下数据写在 `game/data/`）。
2. 把成品包放进 `<游戏目录>/data/mods/`：`dist/<id>.dusk`（开源字体版）或
   `dist/<id>_ique.dusk`（官方字库版，只重排官方位图）。两者覆盖同一批资源，只能装一个。
   `.dusk` 是个 zip：`mod.json`（其 `id` 决定开关名）+ `overlay/<光盘内路径>`，加载时按光盘路径覆盖同名文件。
3. 改 `<游戏目录>/data/config.json`：该包的 `mod.<id>.enabled` 与 `game.enableChineseNameKeyboard` 置 `true`、
   `game.language` 置 `2`，其它 CN 相关 mod 全置 `false`（它们覆盖的是同一批文件）。
   `python scripts/install.py` 会自动完成第 2、3 步（`--variant ique` 装官方字库版），`game.language` 仍需自己设。
4. 验证：标题提示、存档界面、对话、菜单、栏位文字应为简体中文，名字输入界面应显示中文默认名「林克 / 伊波娜」
   （自己改名字只能用拉丁键盘：上游引擎没有中文键盘，那是 dusk-cn 分支的功能）；
   日志在 `%APPDATA%\TwilitRealm\Dusklight\logs\`。
5. 旧存档里的名字存的是旧码位，会显示成错字：新建存档，或重新输入一次名字。

## 技术备忘

### 素材清单

| 文本（`cn/text/`） | 消息数 |
| --- | ---: |
| `bmgres.txt` | 5015（内含 2 个 BMG） |
| `bmgres1.txt` … `bmgres8.txt` | 1820 / 1351 / 508 / 1606 / 1477 / 1357 / 1173 / 1299 |
| `messages.json` | 结构化版本，附来源哈希（早期导出，标签未解析） |
| `tags.json` | 每个归档的标签统计 |

| 字库（`cn/font/`） | 字节 | 说明 |
| --- | ---: | --- |
| `fontres.arc.yaz0` | 908,207 | 从 pak 取出的原样字节（Yaz0 压的 RARC） |
| `rubyres.arc.yaz0` | 890,108 | 同上 |
| `rodan_b_24_22.bfn` | 3,324,480 | 主字体，`fontres.arc` 解压所得 |
| `reishotai_24_22.bfn` | 3,324,480 | 副字体，`rubyres.arc` 解压所得 |

两个内层名与 dusklight 的 `mDoExt_initFont0` / `mDoExt_initFont1` 硬编码要求一致。
文本文件每行 `<消息序号>\t<DAT1 偏移>\t<文本>`，原文换行写作 `\n`（字面两字符），
标签写成 `<Tggcccc>`（高字节 = group），其余控制码写成 `\xNN`。
`res/Msgcn/bmgres99.arc` 内没有 BMG（109 字节的空壳），故无对应文本文件。

### BMG（消息库）

- 头 0x20 字节：`MESG` + `bmg1` + u32 文件大小 + u32 段数 + u8 encoding + 15 字节填充；官中此字节 = `2`。
- 段自偏移 `0x20` 起、按 32 字节对齐：`INF1`（条目表）/ `DAT1`（文本）/ `MID1` / `STR1`。
- 文本 UTF-16BE，以 `0000` 结尾；切分必须按 2 字节对齐找 `0000`，否则形如 `一`（`4E 00`）后接终止符时会错位一字节。
- `encoding` 属文件自声明（`2` 对应 dusklight 的 `JMessage::locale::parseCharacter_2Byte`），不绑语言槽。

### BFN（位图字体）

- 头 0x20 字节：8 字节魔数 + u32 文件大小 + u32 块数 + 16 字节填充。
- 官中 `GLY1`：cell 48×48、texture 256×256、format 0(I4)、numRows/numColumns 5×5、码位 `0x0–0x9DA`（2522 个）。
- 数据是 GX 平铺（tiled）格式；重排字形必须保持平铺，否则渲染器解码错位。

### 引擎侧关键事实（已核对源码）

**标签几何**：`001A`（2 字节 marker）+ 1 字节 size + 3 字节 tag id + 数据；**数据里步进 = `marker + size`、
数据 = `size − 6`，而引擎 `on_tag_` 按 `marker + size + 1` / `size − 5` 算，所以转换时 size 要**减 1**。
判据是 DAT1 消息边界（消息 2866 = `设置为` + 3 个 6 字节 tag + `00 00` = 26 字节，下一条偏移正好 2892）。
早期文档里"size 比 EU 少 1、要 +1"的说法方向相反：那是用「码位在不在字库」当判据，被滑位产生的假码位骗了。

**零字节即结束**：`parseCharacter_ShiftJIS` 遇首字节非前导（`00`）时只吃 1 字节并返回 `0`，
而 `process_character_` 的 `case 0:` 就是消息结束，于是含换行 / tag / ASCII 的消息全在那里被切断（实测 6194/15591 条）。

**引擎插入的码位**（`d_msg_class.cpp` 的 `CHAR_CODE_*`，非日版）：`MSGTAG_REFMARK` 插 1 字节 `0x89`，
而 `0x89` 是前导字节，会把下一个字符的首字节吞掉导致整行错位，所以文本里把它换成字面 `※`；
`STAR/MALE/FEMALE/THIN_*_ARROW` 插的是 `0xB1/0xB2/0xB3/0xB9/0xBC/0xBD/0xBE`，非前导所以安全，
但字库没有这些图标，于是在 `MAP1` 追加别名指向 ★ ♂ ♀ ← → ↑ ↓；组 1/3/5 的 tag 只插 2 字节码位或 ASCII，不需处理。

**字库块结构**：`INF1.fontType` = u16 @块+0x08；`MAP1` method@+0x08、startCode@+0x0A、endCode@+0x0C、
numEntries@+0x0E、表@+0x10（method 3 = 有序 `{u16 码位, u16 字形索引}`，大端）；
`GLY1` startCode@+0x08、endCode@+0x0A、cellW@+0x0C、cellH@+0x0E、texSize@+0x10、fmt@+0x14、
rows@+0x16、cols@+0x18、texW@+0x1A、texH@+0x1C。
`mMaxCode` = 各 `MAP1` 块 `startCode` 的最小值（本字体 `0x20`），所以引擎里 `fontType==2 && mMaxCode>=0x8000`
的「半角转全角 ASCII」分支不生效，ASCII 走 1 字节 + `MAP1` method 0 恒等映射。

## 移植路线

### 根因

dusklight 有一批文本走逐字节字符串操作：`J2DTextBox::draw` 用 `vsnprintf("%s", mStringPtr)` 把面板文本搬进
`J2DPrint::mStrBuff`，`J2DTextBox::drawSelf` 走 `printReturn` 里的 `strlen(pString)`，两者都在 `00` 字节处停，
随后 `J2DPrint::parse` 用 `pString - pStringStart > length` 提前结束循环。
** CN 文本是 UTF-16BE 码位（`开` = `5F 00`），串里出现 `00` 就丢掉后面的字。
实测「按下开始键」只画 2 字，换成无 `00` 的串则 5 字全画。

### 修法

1. 文本重编码进 Shift-JIS 码位空间，BMG 头 `encoding: 2 → 3`（引擎按文件自声明的 encoding 选解码器）。
2. 新码位要同时满足三条：首字节是合法前导（`0x81–0x9F` / `0xE0–0xFC`）；码位 ≥ `0x8800`，否则被
   `change1ByteTo2Bytes` / `changeKataToHira` 改写，后者会把 `0x8340–0x8394` 的片假名码位转成平假名；
   两字节都不为 `00`。实现上只重映射「含 `00` 或首字节非前导」的码位（本次 1850 个），其余保持原值。
3. `00` 开头的 2 字节元素换写法：tag 由 `00 1A size id payload` 改为 `1A (payload+5) id payload`；
   换行 `00 0A` 改为单字节 `0A`；ASCII `00 20`–`00 7E` 改为单字节。
4. 字库 `INF1.fontType` 由 1 改为 2，`MAP1`(method 3) 的码位列同步换成新码位，整表重排保持有序（引擎按码位二分查找），字形索引列不动。
5. 字库必须单页重打包：`JUTResFont::initJoinedTexture` 按 `GLY1.numRows*numColumns` 推页数并拼成一张纹理，
   原始 CN 字库是 101 页 5×5，拼合高度爆表，`CreateTexture` 拿到 `-1` 后 `FATAL aurora::gpu`（首次画字时才崩）。
6. 消息文本原地改写：按 `sorted(distinct offsets)` 分段、段界 = 下一个偏移，文件尺寸、DAT1 偏移、MID1 一律不动
   —— TP 的 BMG 有后缀共享（`Σ 消息长度 > DAT1 容量`），重打包 DAT1 或搬 MID1 都会崩；改短后填空 `00`。
7. 副字体一起换：`mDoExt_getSubFont()` / `getRubyFont()` 用的是 `res/Fonteu/rubyres.arc` 里的 `reishotai_24_22.bfn`
   （存档界面 `fileSel.font[1]`、地图菜单楼层与地名、GameOver、对比度页面都用它），它结构同主字库，跑同一套管线即可。

被取代的旧路线（原样拷 CN 文本、按错的几何给 tag size +1、字库按 EU 度量 ÷2）两处都坏，其成品包 `cn_text_fr.dusk` 已移除。

## 名字与键盘

- 默认名来自消息 `0x381`（`林克`）与 `0x382`（马，`伊波娜`）。
- `game.enableChineseNameKeyboard = true` 后，字库侧给引擎硬编码的 `l_mojiZh[10][65]`（`src/d/d_name.cpp`，
  Shift-JIS 码位，去掉翻页键后 550 格）逐格建 `MAP1` 别名：393 格用原字字形；55 格原字是日式新字体、本身没字形，
  但对应简体字在库里，于是用简体（对照表 `NAME_VARIANT`，在 `patch_sjis_font.py`）；102 格连简体写法也没有，
  于是指向空白字形（U+3000，格子显示为空、仍可按）。
- 键盘的按钮文案是消息 `0x38B/0x38C/0x388/0x38E`；旧编码下 `结束` 前的 tag 会把整串切断，导致按钮空白，现已修好。

## 校验

- `diag_pack.py` 是主判据：按引擎路径解码包内全部文本，再核字库覆盖与键盘每一格，应输出
  「未正常结束 0 条、缺字 0 次」与「名字键盘 … 不符 0」。
- `cmp_msg.py` 逐字节对照包内文本与 pak 原文；`dump_bfn.py` 转储字库块头；
  `find_syms.py` 扫 exe 裸字符串（**dusklight.exe 没有带地址的符号表**，反查调用方要靠引擎源码）。
- 引擎侧探针 `cn-mod/`：CMake 从 `https://github.com/snnh/dusk-cn.git` 拉源码编译出 `.dusk`，
  用 pre/post 钩子记录面板字节与字形码位（`J2DTextBox::draw`、`JUTResFont::drawChar_scale`、`J2DPrint::parse` 等），
  不替换任何函数，编译需 VS 2022 开发环境。旧版探针（含替换 `setString`/`initiate`）必须保持关闭，
  它按 2 字节扫串，与 Shift-JIS 数据同开会让文本错乱。

## 许可与免责

- **代码与文档**：MIT 许可，见 [LICENSE](LICENSE)。
- **不含游戏素材**：官方文本、字库、游戏数据及其派生成品包都不在仓库里；请自备正版
  《塞尔达传说：黄昏公主》（** ** **版）数据，用 `scripts/` 在本地导出。
  这些素材的版权归任天堂 / ** 等原权利人所有，不属于本仓库的许可范围。
- **无关联**：本项目与任天堂、** 及其关联公司无关，未获其授权或认可；仅供学习与研究，使用者自行承担风险。
