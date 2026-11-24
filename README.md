# wx-group-collector

静默微信群消息收集器：基于 [wx4py](https://github.com/claw-codes/wx4py) 监听指定群聊，把每条新消息以 JSONL 格式落盘，供后续处理。**不发送任何消息，被 @ 也不响应。**

## 环境要求

- Windows 10/11
- Python 3.9+
- 微信客户端 4.x（wx4py 已测试 4.1.7.59、4.1.8.29），保持登录
- 运行期间不锁屏、不操作键鼠（wx4py 通过 UI 自动化读取消息）

## 安装

```bat
git clone <repo-url>
cd wx-group-collector
pip install -r requirements.txt
copy config.example.json config.json
```

编辑 `config.json`：

| 字段 | 说明 | 默认 |
|------|------|------|
| `groups` | 要监听的群名列表（微信里显示的完整群名） | 必填 |
| `data_dir` | JSONL 输出目录 | `data` |
| `log_dir` | 日志目录 | `logs` |
| `tail_size` | 每次轮询读取消息列表尾部的条数，刷屏群建议调大 | `32` |
| `tick` / `batch_size` | 轮询调度参数，一般不用动 | `0.1` / `8` |
| `log_each_message` | 控制台打印每条收到的消息 | `true` |

## 运行

```bat
python collector.py
```

启动后每个被监听的群会自动打开一个独立聊天窗口，新消息实时追加写入：

```
data/messages-2026-11-21.jsonl    # 实时收集，按天分文件
```

每行一个 JSON 对象：

```json
{"ts": 1732176000.123, "iso": "2026-11-21T14:00:00.123+08:00", "group": "群名称1", "content": "消息内容", "is_at_me": false, "source": "live"}
```

`Ctrl+C` 停止。

## 回补历史记录（可选）

`collector.py` 只收集启动**之后**的新消息。想导出存量记录：

```bat
python export_history.py --since week
```

输出到 `data/history-<日期>.jsonl`，`since` 可选 `today` / `yesterday` / `week` / `all`。导出过程会滚动群聊窗口，期间不要动键鼠。

## 已知限制（来自微信 4.x UI，非本程序能解决）

- **没有发送者字段**：微信 4.x 的 UI 自动化接口不暴露每条消息是谁发的
- `ts` 是脚本检测到消息的本地时间，不是微信显示的消息时间
- 图片消息先收到“图片”占位文本；`image_copier.py` 会通过微信“复制”菜单保存可读 PNG。语音仍需转写补录，群文件仍需下载后搬运
- 轮询机制下消息量瞬时爆发（超过 `tail_size`）可能丢个别消息
- 长期挂机建议关闭 Windows 自动睡眠、微信保持登录；掉线后重启脚本即可，中间漏掉的消息可用 `export_history.py` 回补

## 本地增强（2026-11-21，基于微信 4.1.8.28 实测调通）

在原 collector 之上新增了三个常驻组件和一键脚本，`start.bat` 全部拉起：

| 组件 | 作用 |
|---|---|
| `collector.py` | 原消息采集；`setup_logging` 改为根 logger 统一格式（wx4py 日志并入 `logs/collector.log` 与控制台） |
| `file_clicker.py` | 发现"文件 X 未下载"消息后，自动右键气泡点菜单"下载"（静默下载，不打开文件） |
| `file_fetcher.py` | 监视微信文件目录 `xwechat_files/<wxid>/msg/file/<yyyy-mm>/`，新文件自动复制到 `data/files/<yyyy-mm>/` 并写 `files-index-<日期>.jsonl`（config.json 的 `wechat_file_dir` 可指定路径） |
| `image_copier.py` | 发现图片消息后右键图片气泡点“复制”，从剪贴板保存为 `data/images/decoded/<yyyy-mm>/*.png`，并写入图片索引 |
| `voice_transcriber.py` | 兜底组件：语音先被抓到占位、转写后到的情况，延迟回读气泡补记到 `data/voice-transcripts-<日期>.jsonl` |

脚本：`start.bat`（讲述人→重启微信→拉起全部组件，详见 `start-collector.ps1`）、`stop.bat`、`check.bat`（自检六项+最后消息时间）。

**关键运行条件**：微信必须是 4.1.8.28，且启动瞬间需讲述人在运行（`start.bat` 已自动处理）；4.1.9+/4.2 对讲述人触发 UIA 树免疫。

**wx4py 补丁**：上游 0.2.1 有两个会导致"静默丢消息"的 bug，已直接修改 venv 内源码修复，详见 [`patches/README.md`](patches/README.md)（含 diff 与完整文件，供 fork wx4py 时提交上游）。注意：`pip/uv` 重装 wx4py 会冲掉补丁。

## 风险提示

wx4py 通过 UI 自动化操作微信客户端，属于非官方用法，存在账号风控风险。建议使用非重要账号，并遵守相关法律法规。
