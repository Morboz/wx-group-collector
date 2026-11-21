# -*- coding: utf-8 -*-
"""微信群文件搬运工。

微信 4.x 收到的文件在用户点击(或开启自动下载)后落盘到:
    C:\\Users\\<用户>\\xwechat_files\\<wxid>\\msg\\file\\<yyyy-mm>\\<文件名>
本脚本轮询该目录,把新出现的文件复制到 data/files/<yyyy-mm>/ 下,
并在 data/files-index-<日期>.jsonl 里记录一条索引,方便和消息记录对应。

不带 UIA,不碰微信,只是文件系统操作,和 collector.py 并行运行。

用法:
    python file_fetcher.py            # 读取同目录 config.json(可选 wechat_file_dir)
    python file_fetcher.py -v         # DEBUG 日志
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

logger = logging.getLogger("file_fetcher")

SCAN_INTERVAL = 5      # 轮询间隔(秒)
STABLE_SCANS = 2       # 连续两次扫描大小一致才认为下载完成
MIN_AGE = 4.0          # 文件修改时间至少 4 秒前,避免拷到半截


def find_wechat_file_dir() -> Path | None:
    """自动探测微信文件目录 xwechat_files\\<wxid>\\msg\\file。"""
    home = Path.home()
    for candidate in home.glob("xwechat_files/*/msg/file"):
        return candidate
    # 常见的自定义位置
    for drive in ("F:", "E:", "D:"):
        for candidate in Path(drive, "xwechat_files").glob("*/msg/file"):
            return candidate
    return None


class FileFetcher:
    def __init__(self, wechat_dir: Path, files_dir: Path, index_dir: Path):
        self.wechat_dir = wechat_dir
        self.files_dir = files_dir
        self.index_dir = index_dir
        self.state_path = BASE_DIR / "data" / ".file_fetcher_state.json"
        # pending: path -> (size, 次数)
        self.pending: dict[str, tuple[int, int]] = {}
        self.copied = 0

    # ---------- 状态持久化:记录"已见过"的文件,重启不重复搬运 ----------
    def load_state(self) -> dict:
        if self.state_path.exists():
            try:
                with self.state_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                logger.warning("状态文件损坏,忽略")
        return {"seen": {}}

    def save_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        tmp.replace(self.state_path)

    # ---------- 扫描 ----------
    def scan_wechat_dir(self) -> list[Path]:
        """列出微信文件目录下的所有文件(跨所有月份子目录)。"""
        result = []
        if not self.wechat_dir.exists():
            return result
        for month_dir in self.wechat_dir.iterdir():
            if not month_dir.is_dir():
                continue
            try:
                for entry in os.scandir(month_dir):
                    if entry.is_file():
                        result.append(Path(entry.path))
            except OSError:
                continue
        return result

    # ---------- 复制与索引 ----------
    def copy_file(self, src: Path) -> Path | None:
        month = src.parent.name  # yyyy-mm
        dest_dir = self.files_dir / month
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        # 同名不同内容时加时间戳后缀,不覆盖
        if dest.exists():
            if dest.stat().st_size == src.stat().st_size:
                return dest  # 已经复制过
            stem, suffix = src.stem, src.suffix
            dest = dest_dir / f"{stem}_{datetime.now():%H%M%S}{suffix}"
        try:
            shutil.copy2(src, dest)
            logger.info("已复制: %s -> %s", src.name, dest)
            return dest
        except Exception:
            logger.exception("复制失败: %s", src)
            return None

    def append_index(self, src: Path, dest: Path) -> None:
        now = time.time()
        rec = {
            "ts": now,
            "iso": datetime.fromtimestamp(now).astimezone().isoformat(timespec="milliseconds"),
            "name": src.name,
            "size": src.stat().st_size,
            "wechat_path": str(src),
            "copied_to": str(dest),
        }
        path = self.index_dir / f"files-index-{datetime.fromtimestamp(now):%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---------- 主循环 ----------
    def run(self, baseline_only: bool = False) -> None:
        state = self.load_state()
        seen: dict = state.setdefault("seen", {})
        first_run = not seen

        files = self.scan_wechat_dir()
        if first_run:
            # 首次运行只建立基线,不搬运历史文件
            for p in files:
                seen[str(p)] = p.stat().st_size
            self.save_state(state)
            logger.info("基线建立完成,已标记 %d 个历史文件(不搬运)", len(seen))
            if baseline_only:
                return

        logger.info("开始监视: %s", self.wechat_dir)
        logger.info("文件落盘到: %s", self.files_dir.resolve())
        logger.info("Ctrl+C 停止")

        while True:
            time.sleep(SCAN_INTERVAL)
            try:
                for p in self.scan_wechat_dir():
                    key = str(p)
                    if key in seen:
                        continue
                    try:
                        stat = p.stat()
                    except OSError:
                        continue  # 消失了(被微信改名/清理)
                    if time.time() - stat.st_mtime < MIN_AGE:
                        continue  # 太新,可能还在下载
                    prev = self.pending.get(key)
                    if prev and prev[0] == stat.st_size:
                        # 大小稳定,搬运
                        dest = self.copy_file(p)
                        if dest:
                            self.append_index(p, dest)
                            self.copied += 1
                        seen[key] = stat.st_size
                        self.pending.pop(key, None)
                        # 定期持久化
                        if self.copied % 5 == 0:
                            self.save_state(state)
                    else:
                        self.pending[key] = (stat.st_size, 0)
            except KeyboardInterrupt:
                raise
            except Exception:
                logger.exception("扫描异常(继续)")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="微信群文件搬运工")
    parser.add_argument("-v", "--verbose", action="store_true", help="DEBUG 日志")
    args = parser.parse_args()

    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    fh = RotatingFileHandler(log_dir / "file_fetcher.log", maxBytes=2 * 1024 * 1024,
                             backupCount=2, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # config.json 可覆盖微信文件目录
    wechat_dir: Path | None = None
    cfg_path = BASE_DIR / "config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            if cfg.get("wechat_file_dir"):
                wechat_dir = Path(cfg["wechat_file_dir"])
        except Exception:
            logger.warning("config.json 读取失败,自动探测微信目录")

    if not wechat_dir or not wechat_dir.exists():
        wechat_dir = find_wechat_file_dir()
    if not wechat_dir or not wechat_dir.exists():
        raise SystemExit("找不到微信文件目录(xwechat_files\\<wxid>\\msg\\file),"
                         "可在 config.json 里加 \"wechat_file_dir\" 指定")

    fetcher = FileFetcher(
        wechat_dir=wechat_dir,
        files_dir=BASE_DIR / "data" / "files",
        index_dir=BASE_DIR / "data",
    )
    try:
        fetcher.run()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("已停止,本次共搬运 %d 个文件", fetcher.copied)


if __name__ == "__main__":
    main()
