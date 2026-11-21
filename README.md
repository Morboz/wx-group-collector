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
- 图片/语音/文件只能收到占位文本（如“[图片]”），拿不到媒体本体
- 轮询机制下消息量瞬时爆发（超过 `tail_size`）可能丢个别消息
- 长期挂机建议关闭 Windows 自动睡眠、微信保持登录；掉线后重启脚本即可，中间漏掉的消息可用 `export_history.py` 回补

## 风险提示

wx4py 通过 UI 自动化操作微信客户端，属于非官方用法，存在账号风控风险。建议使用非重要账号，并遵守相关法律法规。
