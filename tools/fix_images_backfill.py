# -*- coding: utf-8 -*-
"""恢复牛马群今天的图片消息记录 + 清理/补全图片索引。"""
import json
from datetime import datetime
from pathlib import Path

DATA = Path(r"F:\dev\wx-group-collector\data")
MSG = DATA / "messages-2026-11-23.jsonl"
IDX = DATA / "files-index-2026-11-23.jsonl"
IMG_DIR = DATA / "images" / "2026-11"

# 1) 消息流补录:每张归档的牛马原图一条"图片"记录(时间用 .dat 的 mtime)
appended = []
for dat in sorted(IMG_DIR.glob("40255755_*.dat")):
    orig = Path(r"F:\xwechat_files\wxid_9dbnn63f7zfj12_519b\msg\attach") / "4025575597387801f927cf83eee7e1d9" / "2026-11" / "Img" / dat.name.replace("40255755_", "")
    mtime = orig.stat().st_mtime if orig.exists() else dat.stat().st_mtime
    iso = datetime.fromtimestamp(mtime).astimezone().isoformat(timespec="milliseconds")
    appended.append({
        "ts": mtime, "iso": iso, "group": "牛马",
        "content": "图片", "is_at_me": False, "source": "history",
        "image": f"2026-11/{dat.name}",  # 指向归档文件,方便后续处理
    })

with MSG.open("a", encoding="utf-8") as f:
    for r in appended:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"消息流补录 {len(appended)} 条图片记录:")
for r in appended:
    print(f"  {r['iso'][11:19]}  -> {r['image']}")

# 2) 索引清理:删除指向已不存在的 images\\Img\\ 的脏行
lines = [l for l in IDX.read_text(encoding="utf-8").splitlines() if l.strip()]
kept, dropped = [], 0
for l in lines:
    if "images\\Img\\" in l or "images/Img/" in l:
        dropped += 1
        continue
    kept.append(l)

# 3) 补写 5 张牛马图片的正确索引(若尚无)
existing_names = {json.loads(l).get("name") for l in kept}
now = datetime.now().timestamp()
added = 0
for dat in sorted(IMG_DIR.glob("40255755_*.dat")):
    if dat.name.replace("40255755_", "") in existing_names:
        continue
    orig = Path(r"F:\xwechat_files\wxid_9dbnn63f7zfj12_519b\msg\attach") / "4025575597387801f927cf83eee7e1d9" / "2026-11" / "Img" / dat.name.replace("40255755_", "")
    kept.append(json.dumps({
        "ts": now, "iso": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "kind": "image", "name": dat.name.replace("40255755_", ""),
        "size": dat.stat().st_size,
        "wechat_path": str(orig),
        "copied_to": str(dat),
    }, ensure_ascii=False))
    added += 1

IDX.write_text("\n".join(kept) + "\n", encoding="utf-8")
print(f"索引:删脏行 {dropped},补正确行 {added},现有 {len(kept)} 行")
