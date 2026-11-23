# -*- coding: utf-8 -*-
"""把 history 导出中"停机缺口"里的消息合并进 messages jsonl。

缺口判定:live 记录在 20:44 前的最后一条 之后、到当前时间之间,
且该时间段没有 live 记录(停机)。history 记录按微信显示的 HH:MM 落入缺口即补录。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

DATA = Path(r"F:\dev\wx-group-collector\data")
DAY = "2026-11-23"

live_path = DATA / f"messages-{DAY}.jsonl"
hist_path = DATA / f"history-{DAY}.jsonl"

live = [json.loads(l) for l in live_path.read_text(encoding="utf-8").splitlines() if l.strip()]
hist = [json.loads(l) for l in hist_path.read_text(encoding="utf-8").splitlines() if l.strip()]

live_times = [datetime.fromisoformat(l["iso"]) for l in live]
# 停机边界:20:44(本次微信重启前)前最后一条 live
boundary = datetime.fromisoformat(f"{DAY}T20:44:00+08:00")
pre = [t for t in live_times if t < boundary]
gap_start = max(pre) if pre else None
# 20:45 之后是否有 live(重启后新捕获)
post = [t for t in live_times if t >= boundary]
gap_end = min(post) if post else datetime.now().astimezone()

print(f"live 记录 {len(live)} 条")
print(f"缺口: {gap_start} → {gap_end}" if gap_start else "无 pre 边界")

merged = []
skipped_dup_window = 0
skipped_out = 0
for h in hist:
    t_label = (h.get("time") or "").strip()
    if ":" not in t_label:  # 今天的第一条常无时间标签或只有日期
        continue
    try:
        hh, mm = t_label.split(":")[:2]
        t = datetime.fromisoformat(f"{DAY}T{int(hh):02d}:{int(mm.split()[0]):02d}:00+08:00")
    except Exception:
        continue
    if gap_start and t <= gap_start.replace(second=0, microsecond=0):
        skipped_dup_window += 1  # 缺口前:已被 live 覆盖,跳过
        continue
    if t >= gap_end.replace(second=0, microsecond=0):
        skipped_out += 1  # 缺口后:重启后区间,跳过(live 在跑)
        continue
    iso = t.astimezone().isoformat(timespec="milliseconds")
    merged.append({
        "ts": t.timestamp(),
        "iso": iso,
        "group": h.get("group", ""),
        "content": h.get("content", ""),
        "is_at_me": False,
        "source": "history",
    })

print(f"history {len(hist)} 条 → 补录 {len(merged)} 条 (窗口前跳过 {skipped_dup_window}, 窗口后跳过 {skipped_out})")

if merged:
    with live_path.open("a", encoding="utf-8") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("已追加到", live_path)
    for r in merged[:5]:
        print("  ", r["iso"][11:16], r["content"][:30])
