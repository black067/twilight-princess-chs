# 塞尔达传说：黄昏公主汉化 MOD

塞尔达传说：黄昏公主的汉化 mod，用于 [dusklight](https://github.com/TwilitRealm/dusklight)

## 用成品包

**假定你已经准备好了 dusklight 以及可以游玩的镜像**

1. 下载本 mod 的包：[twilitrealm.dev mod 站](https://twilitrealm.dev/mods/) 或 [GitHub Releases](https://github.com/black067/twilight-princess-chs/releases)（美版 / 欧版 / 日版各一份，按你的版本下）
2. 把 `<id>.dusk` 放进引擎的 mods 目录（dusklight 2.x 是 exe 同级的 `mods/`）

> 自己做一份本地化 mod 的步骤见 [构建指南](docs/构建指南.md)。

## 文档

| 文档 | 内容 |
| --- | --- |
| [构建指南](docs/构建指南.md) | 克隆仓库到打包的步骤、译文表格式、打包命令 |
| [实现细节](docs/实现细节.md) | 素材与源文本、译文表与索引、资源怎么生成、打包与安装、引擎侧的硬约束、配置项 |
| [发布指南](docs/发布指南.md) | 上传 Dusklight mod 站的字段规则与手工项 |

## 许可与免责

- **本仓库只有脚本与文档**：输入素材（`input/`）与产物（`dist/`、`work/`）请通过合法途径自行获取；
  输入格式见 [实现细节](docs/实现细节.md)。
- **代码与文档**：MIT 许可，见 [LICENSE](LICENSE)。
- **不含游戏素材**：本仓库不包含任何来自任天堂的文本、字库、游戏数据；版权归各原权利人所有，不属于本仓库的许可范围。
- **开源字体**：字形由思源黑体 / Noto Sans CJK SC 与霞鹜文楷（均 OFL-1.1）渲染；自行构建时，字体文件请自行下载；渲染出的位图随成品包分发。
- **无关联**：本项目与任天堂及其关联公司无关，未获其授权或认可；仅供学习与研究，使用者自行承担风险。
