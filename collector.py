# -*- coding: utf-8 -*-
"""静默微信群消息收集器。

监听指定群聊，把每条新消息追加写入 JSONL 文件（按天分文件）。
不发送任何消息，被 @ 也不响应。

用法:
    python collector.py                     # 读取同目录 config.json
    python collector.py --config other.json
    python collector.py -v                  # 输出 DEBUG 日志
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from wx4py import CallbackHandler, MessageEvent, WeChatClient

BASE_DIR = Path(__file__).resolve().parent

logger = logging.getLogger("collector")


def load_config(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"配置文件不存在: {path}\n"
            f"请复制 config.example.json 为 config.json 并修改 groups 列表"
        )
    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    groups = cfg.get("groups")
    if not groups or not isinstance(groups, list):
        raise SystemExit("config.json 缺少 groups（要监听的群名列表，不能为空）")

    cfg.setdefault("data_dir", "data")
    cfg.setdefault("log_dir", "logs")
    cfg.setdefault("tail_size", 32)
    cfg.setdefault("tick", 0.1)
    cfg.setdefault("batch_size", 8)
    cfg.setdefault("log_each_message", True)
    return cfg


def setup_logging(log_dir: Path, verbose: bool) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    # 统一配置根 logger:collector 与 wx4py 等库的日志走同一格式、同一输出
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers.clear()

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    fh = RotatingFileHandler(
        log_dir / "collector.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # 摘掉 wx4py 各自挂的 handler 并恢复冒泡(它默认 propagate=False),
    # 让其记录统一走根 logger 的格式与输出
    for name, lg in list(logging.root.manager.loggerDict.items()):
        if name.startswith("wx4py") and isinstance(lg, logging.Logger):
            lg.handlers = []
            lg.propagate = True


class JsonlWriter:
    """按天分文件追加写 JSONL。

    每条消息写完即关闭文件句柄，进程被杀也不丢已写入的数据；
    回调在监听单线程内串行执行，无需加锁。
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.count = 0
        self.errors = 0

    def append(self, event: MessageEvent) -> None:
        now = time.time()
        rec = {
            "ts": now,
            "iso": datetime.fromtimestamp(now).astimezone().isoformat(timespec="milliseconds"),
            "group": event.group,
            "content": event.content,
            "is_at_me": event.is_at_me,
            "source": "live",
        }
        path = self.data_dir / f"messages-{datetime.fromtimestamp(now):%Y-%m-%d}.jsonl"
        line = json.dumps(rec, ensure_ascii=False)
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            self.count += 1
        except Exception:
            self.errors += 1
            logger.exception("写 JSONL 失败: %s", path)


def main() -> None:
    # Windows 控制台默认 GBK，避免中文/emoji 日志乱码
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="静默微信群消息收集器")
    parser.add_argument("--config", type=Path, default=BASE_DIR / "config.json",
                        help="配置文件路径，默认同目录 config.json")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出 DEBUG 日志")
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(BASE_DIR / cfg["log_dir"], args.verbose)

    writer = JsonlWriter(BASE_DIR / cfg["data_dir"])

    def on_message(event: MessageEvent):
        writer.append(event)
        if cfg["log_each_message"]:
            preview = event.content.replace("\n", " ")[:80]
            logger.info("[%s] %s", event.group, preview)

    data_dir = (BASE_DIR / cfg["data_dir"]).resolve()
    logger.info("开始收集群消息: %s", ", ".join(cfg["groups"]))
    logger.info("数据目录: %s", data_dir)
    logger.info("Ctrl+C 停止")

    try:
        with WeChatClient(auto_connect=True) as wx:
            wx.process_groups(
                cfg["groups"],
                [CallbackHandler(on_message)],  # auto_reply 默认 False，绝不回复
                block=True,
                tick=cfg["tick"],
                batch_size=cfg["batch_size"],
                tail_size=cfg["tail_size"],
            )
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("已停止，共写入 %d 条，失败 %d 条", writer.count, writer.errors)


if __name__ == "__main__":
    main()
