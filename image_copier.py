# -*- coding: utf-8 -*-
"""通过微信 UI 的“复制”菜单，把图片气泡保存为可读 PNG。

微信 4.x 的 ``msg/attach/.../Img/*.dat`` 是加密文件，不能直接交给视觉模型。
图片气泡本身可以通过右键菜单复制到 Windows 剪贴板，因此这个组件只处理刚
收到、仍在聊天窗口底部可见的图片，不尝试破解微信文件格式。

用法:
    python image_copier.py              # 监听新图片
    python image_copier.py --backfill   # 处理当前消息文件中尚未标记的图片
    python image_copier.py --once       # 处理一轮后退出，便于排障
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import win32clipboard
import win32con
import win32gui

from wx4py.core import uiautomation as uia

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger("image_copier")

POLL_INTERVAL = 3
COPY_SETTLE = 0.6
MENU_TIMEOUT = 3.0
IMAGE_CLASS = "mmui::ChatBubbleReferItemView"
IMAGE_NAME = "图片"


def load_config() -> dict:
    path = BASE_DIR / "config.json"
    if not path.exists():
        raise SystemExit("config.json 不存在")
    cfg = json.loads(path.read_text(encoding="utf-8"))
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
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    fh = RotatingFileHandler(
        log_dir / "image_copier.log", maxBytes=2 * 1024 * 1024,
        backupCount=2, encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)


def find_group_window(group: str):
    """按标题找群聊天窗口。

    只认微信的 Qt 窗口类:标题含群名的浏览器/文档窗口(如飞书"xx群-日报")会
    被 Z 序排前面,一旦误抓,右键复制就会点到别的应用上(2026-11-24 实测踩坑)。
    """
    hits = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        if group not in (win32gui.GetWindowText(hwnd) or ""):
            return
        if win32gui.GetClassName(hwnd) == "Qt51514QWindowIcon":
            hits.append(hwnd)

    win32gui.EnumWindows(callback, None)
    return hits[0] if hits else None


def _top_windows() -> set[int]:
    result: set[int] = set()

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            result.add(hwnd)

    win32gui.EnumWindows(callback, None)
    return result


def _safe_children(control) -> list:
    try:
        return list(control.GetChildren())
    except Exception:
        return []


def _walk(control):
    """遍历菜单树；不同微信版本菜单有时不是顶层窗口的直接子节点。"""
    yield control
    for child in _safe_children(control):
        yield from _walk(child)


def _find_message_list(root):
    try:
        result = root.ListControl(AutomationId="chat_message_list")
        if result.Exists(maxSearchSeconds=1):
            return result
    except Exception:
        pass
    return None


def find_image_bubbles(root) -> list:
    msg_list = _find_message_list(root)
    if msg_list is None:
        return []
    result = []
    # 图片气泡通常是列表直接子节点；递归遍历兼容部分 4.x 版本的包装节点。
    for control in _walk(msg_list):
        try:
            if (control.ClassName or "") != IMAGE_CLASS:
                continue
            if (control.Name or "").strip() != IMAGE_NAME:
                continue
            rect = control.BoundingRectangle
            if rect.right <= rect.left or rect.bottom <= rect.top:
                continue
            result.append(control)
        except Exception:
            continue
    return result


def _menu_item(menu_root, label: str):
    exact = None
    prefix = None
    for control in _walk(menu_root):
        try:
            name = (control.Name or "").strip()
            if name == label:
                exact = control
                break
            if prefix is None and (name.startswith(label + "(") or name.startswith(label + "（")):
                prefix = control
        except Exception:
            continue
    return exact or prefix


def copy_menu_item(before_windows: set[int], owner_root=None) -> bool:
    """在右键菜单中点“复制”，兼容菜单延迟及非顶层菜单。"""
    deadline = time.time() + MENU_TIMEOUT
    while time.time() < deadline:
        current = _top_windows()
        # 新窗口优先；部分版本复用已有菜单窗口，所以随后也扫描全部窗口。
        handles = list(current - before_windows) + list(current)
        seen = set()
        roots = [owner_root] if owner_root is not None else []
        for hwnd in handles:
            if hwnd in seen:
                continue
            seen.add(hwnd)
            try:
                root = uia.ControlFromHandle(hwnd)
                if root is None:
                    continue
                roots.append(root)
            except Exception:
                continue
        for root in roots:
            try:
                if (root.ClassName or "") == "mmui::XMenu":
                    candidates = [root]
                else:
                    # 只在可能的菜单树中查找，避免误点聊天控件中的同名文本。
                    candidates = [c for c in _walk(root) if (c.ClassName or "") == "mmui::XMenu"]
                for menu in candidates:
                    item = _menu_item(menu, "复制")
                    if item is not None:
                        item.Click(simulateMove=False)
                        return True
            except Exception:
                continue
        time.sleep(0.15)
    return False


def dismiss_menu() -> None:
    try:
        import win32api

        win32api.keybd_event(0x1B, 0, 0, 0)
        win32api.keybd_event(0x1B, 0, 2, 0)
    except Exception:
        pass


def _read_clipboard_bytes() -> tuple[str, bytes] | None:
    """读取 PNG 或 CF_DIB，短暂重试以避开微信写剪贴板的窗口。"""
    png_format = win32clipboard.RegisterClipboardFormat("PNG")
    for _ in range(8):
        try:
            win32clipboard.OpenClipboard()
            try:
                if png_format and win32clipboard.IsClipboardFormatAvailable(png_format):
                    data = win32clipboard.GetClipboardData(png_format)
                    if isinstance(data, (bytes, bytearray, memoryview)):
                        return "PNG", bytes(data)
                if win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB):
                    data = win32clipboard.GetClipboardData(win32con.CF_DIB)
                    if isinstance(data, (bytes, bytearray, memoryview)):
                        return "CF_DIB", bytes(data)
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
        time.sleep(0.15)
    return None


def dib_to_bmp(dib: bytes) -> bytes:
    """给 CF_DIB 数据补 BMP 文件头，返回可由 Pillow 读取的字节。"""
    if len(dib) < 12:
        raise ValueError("CF_DIB 数据太短")
    header_size = int.from_bytes(dib[0:4], "little")
    if header_size < 12 or header_size > len(dib):
        raise ValueError(f"不支持的 DIB 头长度: {header_size}")

    # BITMAPCOREHEADER 与 BITMAPINFOHEADER 的字段位置不同。
    if header_size == 12:
        bit_count = int.from_bytes(dib[10:12], "little")
        colors_used = 0
        compression = 0
        palette_entry_size = 3
    else:
        if header_size < 40:
            raise ValueError(f"不支持的 DIB 头长度: {header_size}")
        bit_count = int.from_bytes(dib[14:16], "little")
        colors_used = int.from_bytes(dib[32:36], "little")
        compression = int.from_bytes(dib[16:20], "little")
        palette_entry_size = 4

    palette_count = colors_used or ((1 << bit_count) if bit_count <= 8 else 0)
    extra_masks = 12 if header_size == 40 and compression == 3 else 0
    pixel_offset = 14 + header_size + extra_masks + palette_count * palette_entry_size
    file_size = 14 + len(dib)
    file_header = (
        b"BM" + file_size.to_bytes(4, "little") + b"\x00\x00\x00\x00"
        + pixel_offset.to_bytes(4, "little")
    )
    return file_header + dib


def clipboard_to_png(data_kind: str, data: bytes) -> tuple[bytes, tuple[int, int]]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("缺少 Pillow，请执行 pip install -r requirements.txt") from exc

    raw = data if data_kind == "PNG" else dib_to_bmp(data)
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        size = image.size
        output = io.BytesIO()
        image.save(output, format="PNG")
    return output.getvalue(), size


def copy_latest_image(group: str) -> tuple[bytes, tuple[int, int]] | None:
    hwnd = find_group_window(group)
    if not hwnd:
        logger.warning("[%s] 群窗口不存在，无法复制图片", group)
        return None
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, 9)
        time.sleep(0.5)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.25)
    root = uia.ControlFromHandle(hwnd)
    bubbles = find_image_bubbles(root)
    if not bubbles:
        logger.warning("[%s] 未找到可见图片气泡", group)
        return None
    bubble = bubbles[-1]
    before = _top_windows()
    bubble.RightClick(simulateMove=False)
    if not copy_menu_item(before, owner_root=root):
        dismiss_menu()
        logger.warning("[%s] 右键菜单中未找到“复制”", group)
        return None
    time.sleep(COPY_SETTLE)
    clipboard = _read_clipboard_bytes()
    if clipboard is None:
        logger.warning("[%s] “复制”后剪贴板没有图像数据", group)
        return None
    try:
        return clipboard_to_png(*clipboard)
    except Exception:
        logger.exception("[%s] 剪贴板图像转换失败", group)
        return None


class JsonlTail:
    def __init__(self, data_dir: Path, skip_existing: bool):
        self.data_dir = data_dir
        self.day = datetime.now().strftime("%Y-%m-%d")
        self.seen_lines = 0
        path = self.current_path()
        if skip_existing and path.exists():
            self.seen_lines = sum(1 for _ in path.open("r", encoding="utf-8"))

    def current_path(self) -> Path:
        return self.data_dir / f"messages-{self.day}.jsonl"

    def new_records(self) -> list[dict]:
        day = datetime.now().strftime("%Y-%m-%d")
        if day != self.day:
            self.day = day
            self.seen_lines = 0
        path = self.current_path()
        if not path.exists():
            return []
        result = []
        count = 0
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    count += 1
                    if count <= self.seen_lines:
                        continue
                    try:
                        result.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        self.seen_lines = count
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="把微信图片气泡复制为 PNG")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--backfill", action="store_true", help="启动时处理现有消息文件")
    parser.add_argument("--once", action="store_true", help="处理一轮后退出")
    args = parser.parse_args()
    setup_logging(args.verbose)

    cfg = load_config()
    groups = set(cfg["groups"])
    data_dir = BASE_DIR / cfg.get("data_dir", "data")
    output_dir = data_dir / "images" / "decoded"
    state_path = data_dir / ".image_copier_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except Exception:
        state = {}
    state_is_usable = isinstance(state, dict) and isinstance(state.get("processed", {}), dict)
    processed = state.get("processed", {}) if state_is_usable else {}

    def save_state() -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        tmp = state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"processed": processed}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(state_path)

    # 第一次启动没有状态文件时保留尾部消息，避免组件启动竞态漏掉刚到的图片；
    # 成功处理过一次后，重启默认从文件末尾继续，历史补录显式使用 --backfill。
    tail = JsonlTail(data_dir, skip_existing=state_is_usable and not args.backfill)
    logger.info("开始监听图片消息，监听群: %s", ", ".join(groups))
    logger.info("解码图片目录: %s", output_dir.resolve())

    # 失败不丢弃:JsonlTail 只吐新行,seen_lines 已前移,不加队列的失败记录
    # 永远不会重试。限制重试次数避免窗口长期无气泡时反复抢前台。
    MAX_ATTEMPTS = 10
    RETRY_INTERVAL = 5.0
    pending: dict[str, tuple[dict, int, float]] = {}

    def backfill_image_path(iso: str, png_path) -> None:
        """把 image_path 回写进消息流对应记录,让每条图片消息自带文件路径。

        collector 会向文件追加新行,整文件重写有丢行竞态;用"写前复核行数
        不变才替换,否则重读重试"把窗口压到毫秒级。
        """
        now = datetime.now()
        candidates = [data_dir / f"messages-{now:%Y-%m-%d}.jsonl"]
        from datetime import timedelta
        yesterday = now - timedelta(days=1)
        candidates.append(data_dir / f"messages-{yesterday:%Y-%m-%d}.jsonl")
        for mp in candidates:
            if not mp.exists():
                continue
            for _ in range(5):
                try:
                    lines = mp.read_text(encoding="utf-8").splitlines()
                    n0 = len(lines)
                    out, hit = [], False
                    for ln in lines:
                        r = json.loads(ln)
                        if (not hit and r.get("iso") == iso
                                and r.get("content") == IMAGE_NAME
                                and "image_path" not in r):
                            r["image_path"] = str(png_path)
                            hit = True
                        out.append(json.dumps(r, ensure_ascii=False))
                    if not hit:
                        break  # 该记录不在此文件,换下一天
                    tmp = mp.with_suffix(".tmp")
                    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
                    if len(mp.read_text(encoding="utf-8").splitlines()) == n0:
                        tmp.replace(mp)
                        logger.info("已回写 image_path 到消息记录: %s", iso)
                        return
                    # 行数变了(collector 刚追加),丢弃 tmp 重读重试
                except Exception:
                    pass
                time.sleep(0.5)

    while True:
        for rec in tail.new_records():
            group = rec.get("group", "")
            if group not in groups or rec.get("content") != IMAGE_NAME:
                continue
            key = f"{group}|{rec.get('iso', '')}|{rec.get('ts', '')}"
            if key not in processed and key not in pending:
                pending[key] = (rec, 0, time.time())

        for key, (rec, attempts, due) in list(pending.items()):
            if due > time.time():
                continue
            group = rec.get("group", "")
            result = copy_latest_image(group)
            if result is None:
                attempts += 1
                if attempts >= MAX_ATTEMPTS:
                    logger.warning(
                        "[%s] 图片尝试 %d 次仍失败，放弃: iso=%s（.dat 原件已归档，可人工右键补）",
                        group, attempts, rec.get("iso", ""))
                    del pending[key]
                else:
                    pending[key] = (rec, attempts, time.time() + RETRY_INTERVAL)
                    logger.info("[%s] 图片第 %d/%d 次尝试失败，%s 秒后重试",
                                group, attempts, MAX_ATTEMPTS, RETRY_INTERVAL)
                continue
            png, size = result
            digest = hashlib.sha256(png).hexdigest()
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
            out_dir = output_dir / datetime.now().strftime("%Y-%m")
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"{stamp}_{digest[:12]}.png"
            tmp = out.with_suffix(".tmp")
            tmp.write_bytes(png)
            tmp.replace(out)
            index_day = datetime.now().strftime("%Y-%m-%d")
            index_path = data_dir / f"files-index-{index_day}.jsonl"
            index_rec = {
                "ts": time.time(),
                "iso": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                "kind": "image",
                "name": out.name,
                "size": len(png),
                "copied_to": str(out),
                "decoded_to": str(out),
                "source": "clipboard",
                "msg_iso": rec.get("iso", ""),
                "group": group,
                "sha256": digest,
                "width": size[0],
                "height": size[1],
            }
            with index_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(index_rec, ensure_ascii=False) + "\n")
            processed[key] = str(out)
            save_state()
            pending.pop(key, None)
            backfill_image_path(rec.get("iso", ""), out)
            logger.info("[%s] 图片已保存: %s (%dx%d)", group, out, size[0], size[1])

        if args.once:
            return
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
