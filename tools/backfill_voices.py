# -*- coding: utf-8 -*-
"""把当前群窗口里可见的语音气泡转写补录进 voice-transcripts jsonl。"""
import json
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, r"F:\dev\wx-group-collector\.venv\Lib\site-packages")
import win32gui
from wx4py.core import uiautomation as uia

hwnd = None


def cb(h, _):
    global hwnd
    if "参见大王" in win32gui.GetWindowText(h):
        hwnd = h


win32gui.EnumWindows(cb, None)
if not hwnd:
    print("未找到群窗口")
    sys.exit(1)

root = uia.ControlFromHandle(hwnd)
items = []


def walk(c):
    try:
        if (c.ClassName or "") == "mmui::ChatVoiceItemView":
            items.append(c.Name or "")
        for ch in c.GetChildren():
            walk(ch)
    except Exception:
        pass


walk(root)

recs = []
existing = set()
try:
    with open(r"F:\dev\wx-group-collector\data\voice-transcripts-2026-11-21.jsonl", encoding="utf-8") as f:
        for line in f:
            try:
                existing.add(json.loads(line).get("text"))
            except Exception:
                pass
except FileNotFoundError:
    pass
for name in items:
    m = re.match(r"^语音\s*(\d+)\"\s*秒(?:语音)?\s*(.+)$", name)
    if m and m.group(2) not in existing:
        recs.append({
            "ts": time.time(),
            "iso": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "group": "参见大王",
            "text": m.group(2),
            "duration": int(m.group(1)),
            "orig_iso": "backfill",
        })

with open(r"F:\dev\wx-group-collector\data\voice-transcripts-2026-11-21.jsonl", "a", encoding="utf-8") as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"补录 {len(recs)} 条:")
for r in recs:
    print(f'  [{r["duration"]}"] {r["text"][:30]}')
