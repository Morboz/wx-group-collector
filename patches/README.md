# wx4py 本地补丁(基于 wx4py 0.2.1)

测试环境:**微信 4.1.8.28(Windows)** + "语音自动转文字"开启。
这些改动直接打在本机 venv 的 `wx4py/features/messaging/listener.py` 上,
后续 fork wx4py 时可按此说明整理成正式 PR。

## 文件说明

| 文件 | 用途 |
|---|---|
| `wx4py-0.2.1-listener.patch` | 与 PyPI 原版 0.2.1 的统一 diff(`git apply` 可用) |
| `wx4py-listener.py` | 打满补丁的完整文件(直接对照/拷贝用) |

## 补丁一:MESSAGE_CLASSES 增加 ChatVoiceItemView / ChatBubbleReferItemView(修静默丢语音和图片)

**现象 A**:开启微信"语音自动转文字"后,带转写的语音消息永远不会被监听到。
**现象 B(2026-11-23 发现)**:图片消息在消息流里完全隐形(连占位记录都没有)。

**根因**:语音消息刚到达时气泡类是 `mmui::ChatBubbleItemView`(在白名单);
转写文字几秒后到达,微信把气泡**重渲染为独立的 `mmui::ChatVoiceItemView`**;
图片气泡则是 `mmui::ChatBubbleReferItemView`(实测 Name 为"图片")。
两个类都不在 `MESSAGE_CLASSES` 白名单里,被 `_read_visible_items` 的
`else: continue` 静默丢弃。转写来得快时,监听器连旧形态的气泡都还没轮询到。

**修复**:白名单加入 `"mmui::ChatVoiceItemView"`。修复后带转写的语音
(其 Name 形如 `语音5"秒今天天气太冷了。`)直接进入消息流,转写文字全量可得。

## 补丁二:msg_list 引用定期重建(修重渲染后的静默停摆)

**现象**:消息列表重渲染(语音转写到达、文件下载进度变化等都会触发)之后,
监听器停止上报一切新消息;进程不退、线程不崩、无任何异常日志。

**根因**:`_ListenSession.msg_list` 在会话建立时只获取一次。微信重渲染列表后,
旧 COM 引用被断开但**不会立即失效**——继续返回断开前的旧子元素快照
(非空、永不更新),`_read_visible_items` 因此既不报错也永远读不到新消息。

**修复**(三层防护):

1. `_poll_session` 每隔 20 秒调用 `_reacquire_msg_list` 强制重新定位列表
   (日志:"已刷新消息列表引用")
2. 连续 5 次读到空列表 / 连续 5 次读取异常,同样触发重建
3. `_reacquire_msg_list` 重建时用 **(类名, 文本) 名字级去重**
   (`emitted_names`,保留 30 分钟):
   - 防止重渲染后 runtime_id 变化导致旧消息被当成新消息重复上报
   - 冻结期间真正漏掉的新消息(名字没上报过)会被**自动补报**

## 诊断经验

- 挂死但进程仍在:`py-spy dump --pid <pid>`,健康状态监听线程停在
  `_run_loop` 的 `time.sleep`
- 怀疑被过滤:同一控件上对比"直接 `GetChildren()`"与
  "`_read_visible_items()`"的返回条数,差异即分类过滤问题
- 微信 4.x 的 UI 硬限制:消息气泡是叶子控件,**不暴露发送者**(无昵称、
  无任何稳定 ID);合并转发气泡只暴露折叠摘要文本
