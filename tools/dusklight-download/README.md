# dusklight-download

dusklight 系 Release 的下载工具：上游 `TwilitRealm/dusklight`、中文增强分支 `snnh/dusk-cn` 等。
下载什么由 `config.json` 决定，脚本只含核心逻辑，命令行参数可覆盖配置。

## 目录

```
config.json          下载目标
dist/                下载产物，按 <repo>/<tag>/ 分层（由 scripts/ 重建）
game/                本地运行目录
scripts/             手工维护的脚本（只用标准库）
  common.py            配置与路径解析
  fetch_release.py     按配置拉取各来源 Release 的资产
  run.py               用 game/ 里的 dusklight 启动光盘镜像
  split_zip.py         把单文件切成等长 zip 分卷（7z）
README.md            本文件
```

## 配置

- `dist`：输出根目录，相对本目录或绝对路径，默认 `dist`
- `sources[].repo`：`owner/name`
- `sources[].tag`：具体 tag（如 `v2.0.1`）或 `latest` = 该仓库最新正式 Release
- `sources[].assets`：资产名通配符数组，省略 = 该 Release 全部资产

下载落盘到 `<dist>/<repo>/<tag>/`，多来源、多版本互不覆盖（`latest` 用解析出的实际版本）。

## 下载

脚本只在标准库内实现（`urllib` 下载、`json` 读配置），Windows / macOS / Linux 通用；用仓库根的 venv 时，Windows 是 `.venv\Scripts\python.exe`、Unix 是 `.venv/bin/python`。

```sh
python scripts/fetch_release.py                     # 按配置
python scripts/fetch_release.py --plan              # 只打印计划，不下载
python scripts/fetch_release.py --repo TwilitRealm/dusklight --tag v2.0.1
python scripts/fetch_release.py --assets '*win32-*x86_64*'
python scripts/fetch_release.py --dist D:\dusk-archive
```

- 参数覆盖：`--config` 配置文件（默认 `config.json`）；`--repo` / `--tag` 只跑该来源（配置里有同源时沿用其资产过滤）；`--assets` 本次全部来源的资产过滤，可多次传；`--dist` 输出根目录
- 配置多来源时 `--tag` 须配合 `--repo`；`--assets '*'` 可强制全量
- 目标文件已存在且字节数与上游一致时跳过；不一致时按 Range 续传
- 匿名调用 GitHub API 有每小时次数上限，可先设 `GITHUB_TOKEN` 环境变量

## 运行

解压 `dist/<repo>/<tag>/` 下对应平台的包（Windows 找 `*win32*x86_64*.zip`，Linux/macOS 找 `*-portable.tar.gz`）到 `game/`，然后：

```sh
python scripts/run.py            # 默认用 <dist>/RZDP01.wbfs（dist 取自配置）
python scripts/run.py --disc <镜像>
```

