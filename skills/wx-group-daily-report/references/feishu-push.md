# 飞书推送操作手册（lark-cli）

2026-11-22 安装验证。环境变化（CLI 升级/换机器/换账号）时以 `lark-cli <domain> --help` 和 `lark-cli skills read lark-drive` 为权威。

## 环境与调用

- Node v26.13.1 zip 免安装在 `%LOCALAPPDATA%\Programs\nodejs`（用户 PATH 已持久化）；lark-cli v1.0.100 装在其 `node_modules` 下。
- **Git Bash 下 npm shim 路径解析损坏**，必须 node 直调入口：

```bash
"$LOCALAPPDATA/Programs/nodejs/node.exe" "$LOCALAPPDATA/Programs/nodejs/node_modules/@larksuite/cli/scripts/run.js" <args>
```

- 账号：刘孝羽（**企业账号**，域名 vcnooatcqyil.feishu.cn），App ID `cli_ab8853ea42f81bfa`。
- 授权现状：docs/base/drive 写权限、`space:folder:create` 等已授予；**`search:docs:read`、`space:document:retrieve` 未授予**（增量授权需企业管理员审批）。后果：
  - 不能 `drive +search` / `drive files list` → **一切操作用命令返回的 token，靠下方注册表管理目录，勿依赖列表**。
  - 不要主动发起增量授权；token 失效时用 `auth login --recommend`（原 scope 集合）重走 Device Flow：`--no-wait --json` 拿 URL → `auth qrcode <url> --output qr.png` 生成二维码 → URL 原样发给用户并结束回合 → 用户确认后 `auth login --device-code <code>`。

## 目录 token 注册表（建目录前先查，建完必须更新本表）

| 路径 | folder_token |
|---|---|
| 群消息整理 | `HbuEf3RVGle3Tnd3KYRcZSzxnhh` |
| 群消息整理/2026-11 | `IB8TfiI5glduYrdPinhcEzNSnvf` |
| 群消息整理/2026-11/2026-11-21 | `UNYcfcxtYlrDSNdy18ncae0bn1g` |
| 群消息整理/2026-11/2026-11-23 | `JjObfcv97lnEYld7qC6cohW2n4g` |
| 群消息整理/2026-11/2026-11-24 | `VIywfth9flNPkUd7W5Ec4c7On5b` |

规则：
- 月份目录 `YYYY-MM`：注册表有就直接用；没有才 `drive +create-folder --name YYYY-MM --folder-token HbuEf…`（根 token 固定），成功后把 token 追加进上表。
- 日期目录 `YYYY-MM-DD`：同理，挂在对应月份 token 下。**同一日期的目录/文档若注册表已有记录，说明当天已推送过——重推前先问用户**（无列表权限查不了重复，import 会产生副本）。
- 多目标群（config.json groups ≥2 项）时所有群当天的产物放**同一个日期目录**，文件名带群名区分（`今日报告-<群名>-YYYY-MM-DD`）；单群则不带群名段（保持既有命名）。
- jq 过滤 `+create-folder` 输出会吞掉 token（字段在 `.data.folder_token`），直接看原始 JSON。

## 推送命令

```bash
# 1. 报告 md → 在线文档
drive +import --file "今日报告-YYYY-MM-DD.md" --type docx --folder-token <日目录token> --name "今日报告-YYYY-MM-DD"

# 2. 机构表 CSV → 多维表格（CSV 必须 utf-8-sig BOM，否则中文列名乱码）
drive +import --file "机构结构化表格-YYYY-MM-DD.csv" --type bitable --folder-token <日目录token> --name "机构结构化表格-YYYY-MM-DD"

# 3. 验证（返回 data.data 二维矩阵，行为记录、列为字段值）
base +record-list --base-token <bitable_token> --table-id "数据表" --format json
```

- **同一目录多次 import 必须串行**（并发报 232140101 冲突），两次之间 sleep 3s。
- CSV 用 Python 生成：`open(path,'w',newline='',encoding='utf-8-sig')` + `csv.writer`；首行是 10 列表头，与 md 表格同字段。
- import 成功判据：`job_status_label: "success"`；返回的 `token`/`url` 即交付链接。
- Bitable 导入后默认表名"数据表"。

## 已推送产物存档

| 日期 | 文档 | 多维表格 |
|---|---|---|
| 2026-11-21 | `WvWUdzkcyo73VGxkbs3czFhTnKh` | `KVD9bDQM5ahewTsjxGhcAxfEnse`（12 机构记录，已验证） |
| 2026-11-23 | `Kav0dCWYBo6uoqxPjgEcbBronue`（占位：无新增） | —（跳过） |
| 2026-11-24 | 牛马 `X2FgdeesjoL9VUx6GhWcR8vLnch` · 参见大王 `HPGBdCLDCoZVUzx9sNCceV8wnrh`（极简版） | 牛马 `WWfMbCgIYag7ersv65ecjNiKnKe`（8 机构记录，已验证） |

**CSV 导入已知坑（2026-11-24 发现）**：① 值内含中文逗号"，"的文本列会被 Bitable 按逗号切成多个选项（疑似自动识别为单选/多选字段），如需纯文本显示可在导入后把该字段类型改为"文本"；② 偶发多出 1-2 条空记录（原因未明），导入后用 `+record-list --format ndjson` 核对行数，空行用 `+record-delete` 清理。
