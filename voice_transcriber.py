# -*- coding: utf-8 -*-
"""微信群语音转写补录器。

微信"语音自动转文字"开启后,转写文字会在语音到达几秒后才出现在气泡上,
collector 首次读到的只有 "[语音] N\"" 占位。本组件监控 messages jsonl,
发现语音记录后延迟回头重读该气泡(mmui::ChatVoiceItemView),把转写文字
补记到 data/voice-transcripts-<日期>.jsonl,通过原消息的 iso 时间可对应。

气泡控件文本形如: 语音3"秒语音老公最棒了。
其中 "语音{N}"秒语音" 是前缀,剩余部分即转写文字。

用法:
    python voice_transcriber.py       # 读取同目录 config.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import win32gui

from wx4py.core import uiautomation as uia

BASE_DIR = Path(__file__).resolve().parent

logger = logging.getLogger("voice_transcriber")

POLL_INTERVAL = 4          # 轮询 jsonl 间隔(秒)
FIRST_DELAY = 8            # 发现语音后先等几秒(转写生成需要时间)
RETRY_TOTAL = 60           # 补读总时长上限(秒)
VOICE_RE = re.compile(r'^\[语音\]\s*(\d+)"')
PREFIX_RE = re.compile(r'^语音\s*\d+"\s*秒(?:语音)?\s*')


def load_config() -> dict:
    cfg = json.loads((BASE_DIR / "config.json").read_text(encoding="utf-8"))
    if not cfg.get("groups"):
        raise SystemExit("config.json 缺少 groups")
    return cfg


def setup_logging(verbose: bool) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    fh = RotatingFileHandler(log_dir / "voice_transcriber.log", maxBytes=2 * 1024 * 1024,
                             backupCount=2, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)


def find_group_window(group: str):
    hits = []

    def cb(h, _):
        if group in win32gui.GetWindowText(h):
            hits.append(h)

    win32gui.EnumWindows(cb, None)
    return hits[0] if hits else None


def read_voice_bubble(group: str, duration: int) -> str | None:
    """读取最后一个时长匹配的语音气泡的当前文本,返回去除前缀后的转写(可能为空串)。"""
    hwnd = find_group_window(group)
    if not hwnd:
        return None
    root = uia.ControlFromHandle(hwnd)
    if root is None:
        return None
    found = []

    def walk(ctrl):
        try:
            if (ctrl.ClassName or "") == "mmui::ChatVoiceItemView":
                name = ctrl.Name or ""
                if name.startswith(f'语音{duration}"'):
                    found.append(name)
            for ch in ctrl.GetChildren():
                walk(ch)
        except Exception:
            pass

    walk(root)
    if not found:
        return None
    name = found[-1]
    text = PREFIX_RE.sub("", name).strip()
    return text


class JsonlTail:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.day = ""
        self.seen_lines = 0
        self._sync_day()

    def current_path(self) -> Path:
        return self.data_dir / f"messages-{datetime.now():%Y-%m-%d}.jsonl"

    def _sync_day(self, skip_to_end: bool = True) -> None:
        self.day = f"{datetime.now():%Y-%m-%d}"
        self.seen_lines = 0
        path = self.current_path()
        if path.exists() and skip_to_end:
            with path.open("r", encoding="utf-8") as f:
                for _ in f:
                    self.seen_lines += 1

    def new_records(self) -> list[dict]:
        if f"{datetime.now():%Y-%m-%d}" != self.day:
            self._sync_day(skip_to_end=False)
        path = self.current_path()
        if not path.exists():
            return []
        records, count = [], 0
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    count += 1
                    if count <= self.seen_lines:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        self.seen_lines = count
        return records


def main() -> None:
    parser = argparse.ArgumentParser(description="微信群语音转写补录器")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    cfg = load_config()
    groups = cfg["groups"]
    data_dir = BASE_DIR / cfg.get("data_dir", "data")

    state_path = data_dir / ".voice_transcriber_state.json"
    processed: dict = {}
    if state_path.exists():
        try:
            processed = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            processed = {}

    def save_state():
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(processed, ensure_ascii=False), encoding="utf-8")

    # 首次运行不回补历史语音;重启时跳到末尾只处理新语音
    tail = JsonlTail(data_dir)

    logger.info("开始监控语音消息,监听群: %s", ", ".join(groups))
    logger.info("转写补录到: %s", (data_dir / "voice-transcripts-<日期>.jsonl").resolve())
    logger.info("Ctrl+C 停止")

    while True:
        time.sleep(POLL_INTERVAL)
        try:
            for rec in tail.new_records():
                group = rec.get("group", "")
                if group not in groups:
                    continue
                m = VOICE_RE.match(rec.get("content", ""))
                if not m:
                    continue
                key = rec.get("iso", "")
                if not key or key in processed:
                    continue
                duration = int(m.group(1))
                logger.info("[%s] 发现语音 %d\",延迟回读转写...", group, duration)
                time.sleep(FIRST_DELAY)

                text, ok = "", False
                deadline = time.time() + RETRY_TOTAL
                while time.time() < deadline:
                    text = read_voice_bubble(group, duration)
                    if text is None:
                        # 气泡找不到:窗口关了或已滚出可视区
                        logger.warning("找不到语音气泡(窗口关闭或滚出可视区),放弃")
                        break
                    if text:
                        ok = True
                        break
                    time.sleep(5)  # 转写还没出来,再等等

                if ok:
                    now = time.time()
                    out = {
                        "ts": now,
                        "iso": datetime.fromtimestamp(now).astimezone().isoformat(timespec="milliseconds"),
                        "group": group,
                        "text": text,
                        "duration": duration,
                        "orig_iso": key,
                    }
                    path = data_dir / f"voice-transcripts-{datetime.fromtimestamp(now):%Y-%m-%d}.jsonl"
                    with path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(out, ensure_ascii=False) + "\n")
                    logger.info("转写补录成功: %s", text[:50])
                processed[key] = "ok" if ok else "miss"
                save_state()
        except KeyboardInterrupt:
            raise
        except Exception:
            logger.exception("循环异常(继续)")


if __name__ == "__main__":
    main()
