# -*- coding: utf-8 -*-
"""导出监听启动前的历史聊天记录为 JSONL，用于回补存量数据。

需要微信已登录。导出过程中会打开并滚动目标群聊窗口，请勿操作键鼠。

用法:
    python export_history.py                          # 默认导出今天的记录
    python export_history.py --since week             # 本周以来的记录
    python export_history.py --since all --max-count 2000
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from wx4py import WeChatClient

from collector import BASE_DIR, load_config, setup_logging, logger


def export_group(wx: WeChatClient, group: str, since: str, max_count: int, out: Path) -> int:
    entries = wx.chat_window.get_chat_history(
        group,
        target_type="group",
        since=since,
        max_count=max_count,
    )
    exported_at = time.time()
    with out.open("a", encoding="utf-8") as f:
        for item in entries:
            rec = {
                "exported_at": exported_at,
                "group": group,
                "content": item.get("content", ""),
                "type": item.get("type", ""),
                "time": item.get("time", ""),  # 微信里显示的时间标签，如 "14:05"
                "source": "history",
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="导出群聊历史记录为 JSONL")
    parser.add_argument("--config", type=Path, default=BASE_DIR / "config.json")
    parser.add_argument("--since", choices=["today", "yesterday", "week", "all"],
                        default="today", help="导出的时间范围，默认 today")
    parser.add_argument("--max-count", type=int, default=500, help="单个群的消息条数上限")
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(BASE_DIR / cfg["log_dir"], verbose=False)

    out = BASE_DIR / cfg["data_dir"] / f"history-{datetime.now():%Y-%m-%d}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    with WeChatClient(auto_connect=True) as wx:
        for group in cfg["groups"]:
            logger.info("导出 %s (since=%s) ...", group, args.since)
            try:
                count = export_group(wx, group, args.since, args.max_count, out)
                logger.info("  %s: %d 条", group, count)
            except Exception as exc:
                logger.exception("导出 %s 失败: %s", group, exc)

    logger.info("完成，输出文件: %s", out)


if __name__ == "__main__":
    main()
