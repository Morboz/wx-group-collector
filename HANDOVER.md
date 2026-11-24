# 交接文档:图片链路调试(2026-11-24 08:30)

> **✅ 2026-11-24 晚收尾完成**(commit b38542a):清单 1~5 全部完成——
> E2E 验证通过(19:27 参见大王实测,首次尝试失败后重试队列 5 秒自愈)、
> image_copier 集成 start/stop/check、文档补 decoded 口径、测试群已清理
> (config 只剩牛马,数据/索引/图片/窗口均已清)、已推送。
> 清单 6(群窗口死亡自动重开)未做。
> **新增运维红线:collector 控制台窗口绝不可点选文字**——QuickEdit 选中状态会
> 冻结日志输出线程(监听线程卡死在 StreamHandler.emit),表现是
> "已刷新消息列表引用"停更而进程仍活着;处置:重启 collector(杀控制台宿主
> powershell+python 全树,再照 start-collector.ps1 拉起),勿重启微信。

交接目标:下一个 agent 接手**图片功能**的收尾验证与集成。前一个会话已完成
全部技术攻坚,剩余的是「最后一步验证 + 集成 + 清理」,均已列在文末清单。

---

## 一、系统现状(接手时)

**运行中的组件**(每组件 2 个 python 进程=uv venv 跳板器+解释器,属正常,勿误判重复):

| 组件 | 作用 | 状态 |
|---|---|---|
| collector.py | 消息采集(控制台可见) | ✅ 运行中,双群监听(牛马+参见大王) |
| file_fetcher.py | 文件+图片 .dat 归档到 data\files\ 与 data\images\,索引带 kind 和 msg_iso | ✅ |
| file_clicker.py | "文件 X 未下载"自动右键下载 | ✅ |
| voice_transcriber.py | 语音转写兜底补录 | ✅ |
| **image_copier.py** | **图片解码:右键"复制"→剪贴板→PNG**(本文档主角) | ✅ 08:27 起 |

- 微信:**4.1.8.28**(必须!4.1.9+/4.2 对讲述人免疫),登录账号 wxid_9dbnn63f7zfj12_519b
- config.json:`groups: ["牛马","参见大王"]`——**参见大王是临时加的测试群,收尾时要移除**
- 监听数据:data\messages-YYYY-MM-DD.jsonl

## 二、图片链路已完成的成果

### 1. 消息流记录(已修,已验证)
图片气泡类 `mmui::ChatBubbleReferItemView`(Name="图片")原不在 wx4py 的
MESSAGE_CLASSES 白名单 → 消息流完全隐形。已补进 venv 的
`wx4py/features/messaging/listener.py`(详见 patches/README.md)。

### 2. 原件归档(已修,已验证)
微信自动下载图片到 `F:\xwechat_files\<wxid>\msg\attach\<会话哈希>\<yyyy-mm>\Img\*.dat`
(`_t.dat`=缩略图)。file_fetcher 已扩展:原图归档到 `data\images\<yyyy-mm>\`
(文件名带会话哈希前缀防跨群重名),索引(files-index)记 `kind:"image"` + `msg_iso`
(归档时反查消息流最近的"图片"记录,精确回链)。
**会话哈希:牛马=40255755…,参见大王=896f0ef2…**

### 3. .dat 加密结论(已探明,勿重复劳动)
- 微信 4.x 新加密:非 3.x 单字节 XOR(256 key 暴力无命中),全文件无内嵌图片魔数
- **解不开,但不需要解**——走 UI 复制路线(下条)
- .dat 是只读属性,脚本删/移前要 chmod

### 4. 图片解码:image_copier.py(已验证一次成功)
**注意:此文件是"另一个会话/自动化环境"(daily-report skill 所在的 .agents 环境)
于 11-24 00:34 写成、06:01 拉起的**,不是本会话产物。本会话自研的
image_decoder.py 已删除(两解码器并存会抢鼠标、互相搞挂窗口,已吃过亏)。

验证成功的完整配方(2026-11-24 08:18 实测,产出 972KB PNG+带 sha256/尺寸的索引):

```
窗口临时 TOPMOST(防遮挡!SetWindowPos -1,用后恢复 -2)
→ 落点 WindowFromPoint 验证 == 群窗口句柄(被浏览器/ZCode 窗口遮挡是最大坑)
→ SetCursorPos + 0.4s 悬停 + 右键(纯 mouse_event 不带悬停可能不弹菜单)
→ 菜单在聊天窗口内部找:类 mmui::XMenuView(注意:不是文件的 XMenu!),
   Name=="复制",要求屏幕内坐标(树里有 -31941 的离屏模板节点,别点它)
→ 点击"复制" → 剪贴板优先 CF_HDROP(微信会写解码后的临时 JPG 到
   temp\RWTemp\2026-11\<哈希>\,pywin32 返回文件名元组,直接复制文件即可)
   → 次选 image/png 字节 → 再次 CF_DIB(拼 BMP 头:偏移=14+头长+调色板,
     注意 DIB 头 8-12 字节是高度不是偏移,别读错)
→ 落盘 data\images\decoded\<yyyy-mm>\ + 写 files-index(kind:image, decoded:true)
```

**失败模式速查**(前会话 v1→v9 全踩过):
- 右键没反应 → 落点被遮挡(WindowFromPoint 验证)或没带悬停
- 菜单抓不到 → 在找 XMenu 而不是 XMenuView;或在做"新窗口 diff"(它是窗口内控件)
- 点了没效果 → 点中离屏模板节点(坐标 -31941)
- 图片气泡矩形 (0,0,0,0) → 虚拟化边界,气泡在视口顶部,向下滚一点重新找
- strftime("%L") 不存在,毫秒用 microsecond//1000

## 三、待办清单(按序执行)

1. **最终 E2E 验证**(差最后一步!):让用户往"参见大王"发一张图,确认:
   消息流出现"图片"记录 → .dat 归档+msg_iso → image_copier 产出 decoded PNG+索引。
   注意 image_copier 有 `--backfill` 模式可补处理漏掉的。
2. **集成脚本**:image_copier 加入 start-collector.ps1 / stop.bat / check-status.ps1
   (照 file_clicker 的样子;stop.bat 的 wmic 不能用带括号 OR,逐条写)。
3. **文档**:DATA_GUIDE.md 和 skill 的 references/data-format.md 补 decoded 图片
   说明(索引里 decoded:true 的条目 copied_to 是可直接看的 PNG;报告 agent 可用视觉读图)。
4. **清理测试群**:config.json 去掉"参见大王";删今天测试产生的参见大王消息记录/
   索引/图片文件(参照 11-23 晚的清理流程:按 group 字段过滤消息、按哈希前缀删文件);
   关闭参见大王窗口。
5. **提交推送**(用户是仓库作者 Morboz,SSH 已配;提交身份用
   Morboz <Morboz@users.noreply.github.com>)。
6. 可选优化:listener 加"群窗口死亡自动重开"(现在窗口被关只会无限报
   "事件无法调用任何订户",要重启 collector 才能恢复)。

## 四、运维要点(必读)

- 一键:start.bat / stop.bat / check.bat(**自动化里直调 ps1,check.bat 带 pause 会卡死**)
- 微信重启后自动点"进入微信"**已连续失败 4 次**,失败后流程:用户手动登录 →
  直接拉五组件(不重启微信;讲述人在微信进程启动时已生效,手动登录不影响树)
- 关讲述人时认准窗口标题,别误关微信(发生过)
- **多会话/多 agent 并行操作同一微信 = 灾难**(互相抢鼠标、搞挂窗口);
  daily-report 的 06:00 自动化也会动这套系统,改动前看它的 skill:
  C:\Users\xx\.agents\skills\wx-group-collector… 的 SKILL.md 与 DATA_GUIDE.md
- 诊断工具:F:\dev\_probe\uia_probe.py(树体检,节点<5=没加载)、
  image_copy_v9.py(可用配方参考)、menu_watcher.py(人肉操作时抓 UIA 现场的技术)
- **图片补收(2026-11-24 实战经验)**:工具在 F:\dev\_probe\copy_at.py(按屏幕坐标
  对图片气泡右键复制)+ 截屏(PIL.ImageGrab→Read 看图)人工测坐标的闭环。
  要点:①UIA 图片"行"矩形是全行宽,直接点行中心会落在图右侧空白处不出菜单,
  必须按截图测图片实际位置;②消息流里的时间分隔条=mmui::ChatItemView(Name 即
  "14:33"/"上午11:37"),用"图片上方最近时间标签"可精确识别每张图的归属消息;
  ③同一标签下多张图按文档序对号;④复制前先清空剪贴板,防止读到上一张的旧数据
  (InvokePattern 点击是空操作,要用真实鼠标点击);⑤滚轮惯性距离不定,大步滚后
  要以"画面不再变化"判断到底;⑥群窗口标题会与浏览器/文档窗口撞名,find_group_window
  已改为只认 Qt 窗口类(image_copier.py 同款修复)。
- 采集器静默停摆排查:py-spy dump(venv 已装)看监听线程是否停在 sleep;
  collector.log 里"已刷新消息列表引用"应约 20 秒一条,停更=循环死了
- Git Bash 传 Windows 路径参数要 MSYS_NO_PATHCONV=1;中文输出乱码是显示层问题,
  数据本身 UTF-8 正常

## 五、相关文件地图

```
F:\dev\wx-group-collector\           仓库(git 已推到 github.com/Morboz/wx-group-collector)
├── collector.py / file_fetcher.py / file_clicker.py / voice_transcriber.py / image_copier.py
├── start.bat / stop.bat / check.bat + start-collector.ps1 / check-status.ps1
├── patches\        wx4py 三处补丁的 diff+全文+说明(pip 重装会冲掉)
├── tools\          排障脚本(uia_probe 等)
├── DATA_GUIDE.md   数据格式权威文档
├── data\
│   ├── messages-*.jsonl          消息流
│   ├── files-index-*.jsonl       文件/图片索引(kind=file|image, msg_iso, decoded)
│   ├── images\<yyyy-mm>\*.dat    加密原件归档
│   └── images\decoded\<yyyy-mm>\ 解码后的可看 PNG/JPG
└── .venv\          uv 建;wx4py 源码已打补丁
F:\dev\_probe\      调试探针(v1-v9 演化过程,uia_probe 最常用)
C:\Users\xx\.agents\skills\wx-group-daily-report\  日报 skill(06:00 自动化所在环境)(skill 真实目录;仓库 skills/wx-group-daily-report 是指向它的 junction,已纳入本仓库版本管理,改哪边等效)
```
