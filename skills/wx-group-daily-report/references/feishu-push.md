# 飞书推送操作手册（lark-cli）

2026-11-22 安装验证。环境变化（CLI 升级/换机器/换账号）时以 `lark-cli <domain> --help` 和 `lark-cli skills read lark-drive` 为权威。**2026-11-25 起两项结构变更**：① 机构数据 = 唯一累积总表，每日追加记录（无每日表格文件/多维表格，CSV 导入废弃）；② 云盘扁平化：报告文档直接放月份目录、文档名 = `YYYY-MM-DD`，**不建日期级目录**（历史日期目录已删除）。

## 环境与调用

- Node v26.13.1 zip 免安装在 `%LOCALAPPDATA%\Programs\nodejs`（用户 PATH 已持久化）；lark-cli v1.0.100 装在其 `node_modules` 下。
- **Git Bash 下 npm shim 路径解析损坏**，必须 node 直调入口：

```bash
"$LOCALAPPDATA/Programs/nodejs/node.exe" "$LOCALAPPDATA/Programs/nodejs/node_modules/@larksuite/cli/scripts/run.js" <args>
```

- 账号：刘孝羽（**企业账号**，域名 vcnooatcqyil.feishu.cn），App ID `cli_ab8853ea42f81bfa`。
- 授权现状：docs/base/drive 写权限、`space:folder:create` 等已授予；**`search:docs:read`、`space:document:retrieve` 未授予**（增量授权需企业管理员审批）。后果：
  - 不能 `drive +search` / `drive files list` / `+pull` 列目录 → **一切操作用命令返回的 token，靠下方注册表管理目录，勿依赖列表**。
  - 不要主动发起增量授权；token 失效时用 `auth login --recommend`（原 scope 集合）重走 Device Flow：`--no-wait --json` 拿 URL → `auth qrcode <url> --output qr.png` 生成二维码 → URL 原样发给用户并结束回合 → 用户确认后 `auth login --device-code <code>`。

## 目录 token 注册表（建目录前先查，建完必须更新本表）

| 路径 | folder_token |
|---|---|
| 群消息整理 | `HbuEf3RVGle3Tnd3KYRcZSzxnhh` |
| 群消息整理/2026-11 | `IB8TfiI5glduYrdPinhcEzNSnvf` |

规则：
- 目录只有两级：根目录 → 月份目录。报告文档直接放月份目录下，**文档名 = `YYYY-MM-DD`**（多目标群 = `YYYY-MM-DD-<群名>`），**不建日期目录**（2026-11-25 起扁平化，历史日期目录已删除）。
- 月份目录 `YYYY-MM`：注册表有就直接用；没有才 `drive +create-folder --name YYYY-MM --folder-token HbuEf…`（根 token 固定），成功后把 token 追加进上表。
- **当天是否已推送过**：查下方"已推送产物存档"表；注册表/存档已有该日期记录说明推过——重推前先问用户（无列表权限查不了重复，import 会产生副本）。
- jq 过滤 `+create-folder` 输出会吞掉 token（字段在 `.data.folder_token`），直接看原始 JSON。

## 机构结构化表格-总表（唯一累积表，2026-11-25 起）

| 项 | 值 |
|---|---|
| base_token | `IhwWbs5c0aZlAys2oDIcL6annKb` |
| URL | https://vcnooatcqyil.feishu.cn/base/IhwWbs5c0aZlAys2oDIcL6annKb |
| 表名 | `机构记录`（table_id `tblDq3a1QmRtiVgP`，11 个字段全 text，建表时显式指定） |
| 字段顺序 | **机构（首列主键，飞书默认冻结首列）**、机构背景、基金情况、基金规模、内部分工、汇报线、投资方向、最近投的项目、谁投的、群内动态（补充）、**更新日期（末列）** |
| 现状 | 2026-11-25 建成 v3 结构（按机构一行、就地更新 + 更新日期末列；无＊、"产业资本"统一用语）：11-24 共 8 条 + 11-25 共 30 条 = 38 条（已验证） |

写入规则（**按机构一行、就地更新**，2026-11-25 起）：
- 每班次先 `+record-list` 拉全表，建"机构→record_id"映射；records.json 由整理阶段直接产出（见 SKILL.md 产物二，字段顺序按上表）。不产每日表格 md、不建每日多维表格。
- 分流写入：**新机构** → `+record-batch-create`（`{"create_records":[{…},…]}`）；**已有机构** → 新信息合并进该行后 `+record-batch-update`（`{"update_records":{"recX":{…}}}`，按 record_id）。单批 ≤200 条，text 字段直接传字符串。
- **凡建行或更新行，`更新日期` 一律置为本次运行日**（文本，如 "2026-11-25"）。这是用户明确口径：信息更新必须同步更新该列。
- `+record-upsert` **不支持按业务键自动 upsert**（必须带 --record-id 才是更新），勿直接用；分流判断自己做。
- 同日重跑：更新是幂等的（同值重写无害），但建行前必须查映射，防止同一机构重复建行。
- 用语统一：不写"产业机构"，一律"产业资本"；不使用＊标记（信息载体在"群内动态（补充）"用文字说明）。
- 写入后 `+record-list` 核对：新增行数 + 更新行数 = 预期记录数。batch-create **不会产生空行**。
- 多目标群（config.json groups ≥2）时：先往总表加一个"群"text 字段再写入，记录带群名；单群模式不需要该字段。
- 字段名不匹配会整批报错（不会静默建字段），按报错核对字段名后重试。
- `<skill目录>/scripts/md_table_to_records.py` 仅用于从历史 md 表格回填转换（现流程不再产生该 md；脚本输出已是 v3 字段序，`更新日期` 在末列）。

## 推送命令

```bash
# 1. 报告 md → 在线文档（直接挂月份目录，文档名=日期；多群 = "YYYY-MM-DD-<群名>"）
drive +import --file "今日报告-YYYY-MM-DD.md" --type docx --folder-token <月份token> --name "YYYY-MM-DD"

# 2. 机构记录 → 总表（新机构建行 / 已有机构就地更新，均带 更新日期=运行日；分流见上节）
base +record-batch-create --base-token IhwWbs5c0aZlAys2oDIcL6annKb --table-id "机构记录" --json "$(cat records_new.json)"
base +record-batch-update --base-token IhwWbs5c0aZlAys2oDIcL6annKb --table-id "机构记录" --json "$(cat records_update.json)"

# 3. 验证（返回 data.data 二维矩阵，行为记录、列为字段值；核对总行数与新增行数）
base +record-list --base-token IhwWbs5c0aZlAys2oDIcL6annKb --table-id "机构记录" --format json
```

- **同一目录多次 import 必须串行**（并发报 232140101 冲突），两次之间 sleep 3s；总表追加（base 域）与报告导入（drive 域）互不冲突。
- import 成功判据：`job_status_label: "success"`；返回的 `token`/`url` 即交付链接。
- 云盘改名/移动/删除：`drive +update-title` / `+move` / `+delete`（delete 属 high-risk 需 `--yes`，仅用户明确要求时用）。

## 已推送产物存档

| 日期 | 报告文档（月份目录平铺，名=日期） | 说明 |
|---|---|---|
| 2026-11-21 | —（用户已删） | 每日表也已删；数据源为「参见大王」群（已退订） |
| 2026-11-23 | —（用户已删） | 占位报告（无新增） |
| 2026-11-24 | `X2FgdeesjoL9VUx6GhWcR8vLnch`（名"2026-11-24"） | 原「牛马」日报（2026-11-25 移入月份目录并改名）；参见大王版与每日表已删，8 条记录在总表 |
| 2026-11-25 | `Nwf2dgBpaoaQdPxcOXbcvCNAnhh`（名"2026-11-25"） | 同上移入改名；每日表已删（旧版仅 5 条，完整 30 条在总表） |
| 总表 | — | `IhwWbs5c0aZlAys2oDIcL6annKb`（唯一累积表，每日追加，见上节） |

**CSV 导入已知坑（历史遗留，2026-11-24/25 确认；现流程已不走 CSV 导入）**：① 值内含中文逗号"，"的文本列会被 Bitable 按逗号切成多个选项（疑似自动识别为单选/多选字段），如需纯文本显示可在导入后把该字段类型改为"文本"；② **导入默认建满 10 行网格**，数据不足 10 条时剩余为空记录——每次导入后必须 `+record-list --format ndjson` 核对并把空行 `+record-delete` 清掉（已两次复现）。

**建表撞名坑（2026-11-25 确认）**：`base +base-create` 的 `--table-name` 不能用"数据表"——CLI 会先建应用（自动带出同名默认表）再建自定义表，撞名后中途失败且**残留一个空应用，token 无法找回**（当前根目录下仍有一个这样的空《机构结构化表格-总表》待用户手动删）。用其他表名（如"机构记录"）则 CLI 建完自动删除默认表，一次成功。
