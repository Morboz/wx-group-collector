# 运维工具集

排障与数据抢救用的脚本快照(路径/群名/哈希按当时场景硬编码,复用时先改)。
统一用 `.venv\Scripts\python.exe tools\<脚本>` 运行。

| 脚本 | 用途 |
|---|---|
| `uia_probe.py` | 微信 UIA 控件树体检:节点数 <5 = 树未加载(讲述人没在微信启动时运行/版本不对);也可验证懒加载。排障第一步 |
| `backfill_voices.py` | 从群窗口可见的语音气泡手工回捞转写到 voice-transcripts jsonl(带去重) |
| `merge_backfill.py` | 停机缺口回补:export_history 导出的记录按时间窗去重合并进 messages jsonl |
| `fix_images_backfill.py` | 图片消息记录补录 + files-index 脏行清理(一次性场景快照) |

经验:微信 4.x 消息气泡类名(诊断"某类消息隐形"时用)——
文字 `ChatTextItemView`、文件 `ChatBubbleItemView`、语音 `ChatVoiceItemView`、
图片 `ChatBubbleReferItemView`;不在 listener 的 MESSAGE_CLASSES 白名单就会被静默丢弃。
