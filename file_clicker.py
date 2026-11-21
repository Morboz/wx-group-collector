# -*- coding: utf-8 -*-
"""微信群文件自动下载器。

监控 collector 写出的 messages-<日期>.jsonl,发现"文件 X 未下载"的消息后,
在群聊窗口里定位该文件气泡,右键 -> 菜单"下载",让微信静默下载
(不打开文件)。下载完成后由 file_fetcher.py 负责复制到 data/files/。

注意:点击瞬间会把群窗口短暂置前并移动鼠标,约 1~2 秒,期间不要碰键鼠。

用法:
    python file_clicker.py          # 读取同目录 config.json
    python file_clicker.py -v
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

logger = logging.getLogger("file_clicker")

POLL_INTERVAL = 4          # 轮询 jsonl 间隔(秒)
CLICK_TIMEOUT = 30         # 等待下载完成(气泡失去"未下载")的最长秒数
UNLOAD_RE = re.compile(r"文件\s+(.+?)\s+未下载")


def load_config() -> dict:
    cfg_path = BASE_DIR / "config.json"
    if not cfg_path.exists():
        raise SystemExit("config.json 不存在")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
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
    fh = RotatingFileHandler(log_dir / "file_clicker.log", maxBytes=2 * 1024 * 1024,
                             backupCount=2, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)


def find_group_window(group: str):
    """按标题找群聊独立窗口。"""
    hits = []

    def cb(h, _):
        if group in win32gui.GetWindowText(h):
            hits.append(h)

    win32gui.EnumWindows(cb, None)
    return hits[0] if hits else None


def find_bubble(root, filename: str):
    """在群窗口控件树里找最后一个匹配"文件名 + 未下载"的气泡(最新一条)。"""
    found = []

    def walk(ctrl):
        try:
            name = ctrl.Name or ""
            if "ChatBubble" in (ctrl.ClassName or "") and filename in name and "未下载" in name:
                found.append(ctrl)
            for ch in ctrl.GetChildren():
                walk(ch)
        except Exception:
            pass

    walk(root)
    return found[-1] if found else None


def _top_windows() -> set:
    wins = set()

    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            wins.add(h)

    win32gui.EnumWindows(cb, None)
    return wins


def click_download_menu_item(before_windows: set):
    """在右键弹出的新顶层窗口(mmui::XMenu)里点'下载'(精确匹配,避开'下载到...')。

    用"右键前后对比新出现的窗口"定位菜单——直接遍历桌面根的孩子
    拿不到新弹出的菜单窗口。
    """
    for _ in range(10):  # 菜单出现可能稍有延迟
        for h in (_top_windows() - before_windows):
            menu = uia.ControlFromHandle(h)
            if not menu or (menu.ClassName or "") != "mmui::XMenu":
                continue
            for item in menu.GetChildren():
                if (item.Name or "").strip() == "下载":
                    item.Click(simulateMove=False)
                    return True
        time.sleep(0.2)
    return False


def dismiss_menu() -> None:
    """兜底:按 Esc 关闭可能残留的菜单。"""
    import win32api
    win32api.keybd_event(0x1B, 0, 0, 0)
    win32api.keybd_event(0x1B, 0, 2, 0)


def trigger_download(group: str, filename: str) -> bool:
    """右键目标气泡并点击菜单'下载'。"""
    hwnd = find_group_window(group)
    if not hwnd:
        logger.warning("[%s] 群窗口不在(被关了?),无法下载 %s", group, filename)
        return False

    # 窗口最小化时先还原,并置前以保证点击落点正确
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
        time.sleep(0.5)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.3)

    root = uia.ControlFromHandle(hwnd)
    bubble = find_bubble(root, filename)
    if bubble is None:
        logger.info("[%s] 没找到 %s 的未下载气泡(可能已下载),跳过", group, filename)
        return True  # 视为已处理

    before = _top_windows()
    bubble.RightClick(simulateMove=False)
    time.sleep(1.0)
    if not click_download_menu_item(before):
        dismiss_menu()
        logger.warning("右键菜单里没找到'下载'项: %s", filename)
        return False
    logger.info("已点击菜单'下载': %s", filename)
    return True


def wait_downloaded(group: str, filename: str, timeout: int = CLICK_TIMEOUT) -> bool:
    """等待气泡失去'未下载'状态。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = find_group_window(group)
        if hwnd:
            root = uia.ControlFromHandle(hwnd)
            if root and find_bubble(root, filename) is None:
                return True
        time.sleep(2)
    return False


class JsonlTail:
    """跟随 messages-<日期>.jsonl,跨天自动切换新文件。"""

    def __init__(self, data_dir: Path, skip_existing: bool):
        self.data_dir = data_dir
        self.day = ""
        self.seen_lines = 0
        # 首次运行从头读(补处理挂着的未下载文件);有状态文件的重启则跳到末尾
        self._jump_to_now(skip_to_end=skip_existing)

    def current_path(self) -> Path:
        return self.data_dir / f"messages-{datetime.now():%Y-%m-%d}.jsonl"

    def _jump_to_now(self, skip_to_end: bool = True) -> None:
        self.day = f"{datetime.now():%Y-%m-%d}"
        path = self.current_path()
        self.seen_lines = 0
        if not path.exists():
            return
        if skip_to_end:
            with path.open("r", encoding="utf-8") as f:
                for _ in f:
                    self.seen_lines += 1

    def new_records(self) -> list[dict]:
        if f"{datetime.now():%Y-%m-%d}" != self.day:
            self.day = f"{datetime.now():%Y-%m-%d}"
            self._jump_to_now(skip_to_end=False)  # 新的一天从头读
        path = self.current_path()
        if not path.exists():
            return []
        records = []
        count = 0
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
    parser = argparse.ArgumentParser(description="微信群文件自动下载器")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    cfg = load_config()
    groups = cfg["groups"]
    data_dir = BASE_DIR / cfg.get("data_dir", "data")

    # 持久化"已处理"记录,重启后不重复点击
    state_path = data_dir / ".file_clicker_state.json"
    processed: dict[str, str] = {}
    if state_path.exists():
        try:
            processed = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            processed = {}

    def save_state():
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(processed, ensure_ascii=False), encoding="utf-8")

    tail = JsonlTail(data_dir, skip_existing=state_path.exists())
    logger.info("开始监控未下载文件,监听群: %s", ", ".join(groups))
    logger.info("Ctrl+C 停止")

    while True:
        time.sleep(POLL_INTERVAL)
        try:
            for rec in tail.new_records():
                group = rec.get("group", "")
                if group not in groups:
                    continue
                m = UNLOAD_RE.search(rec.get("content", ""))
                if not m:
                    continue
                filename = m.group(1).strip()
                key = f"{rec.get('iso', '')}|{filename}"
                if key in processed:
                    continue
                logger.info("[%s] 发现未下载文件: %s", group, filename)
                ok = False
                for attempt in range(2):
                    if trigger_download(group, filename):
                        if wait_downloaded(group, filename):
                            ok = True
                            break
                        logger.warning("等待下载超时(第 %d 次): %s", attempt + 1, filename)
                    else:
                        time.sleep(3)
                processed[key] = "ok" if ok else "failed"
                save_state()
                if ok:
                    logger.info("下载完成: %s(等 file_fetcher 自动搬运)", filename)
                else:
                    logger.error("自动下载失败: %s,请手动双击该文件", filename)
        except KeyboardInterrupt:
            raise
        except Exception:
            logger.exception("循环异常(继续)")


if __name__ == "__main__":
    main()
