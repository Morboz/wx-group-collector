# 把机构结构化表格 md（10 列，历史/手工格式）转成总表 batch-create 的 records.json（回填场景专用，日常流程直接产 records.json）。
# 用法: python md_table_to_records.py <机构结构化表格-YYYY-MM-DD.md> <YYYY-MM-DD> <输出records.json>
# 输出: v3 字段序 {"create_records":[{"机构":…,…,"群内动态（补充）":…,"更新日期":"YYYY-MM-DD"},…]}，
#       供 base +record-batch-create --json "$(cat …)" 使用。
# 校验失败（表头不符/行列数不对）时非零退出，禁止带病写入。
import json
import sys

MD_FIELDS = ["机构", "机构背景", "基金情况", "基金规模", "内部分工", "汇报线", "投资方向", "最近投的项目", "谁投的", "今日群内动态（补充）"]
# md 表头 → 总表字段（末列去"今日"，日期改名"更新日期"置于末列）
RECORD_FIELDS = MD_FIELDS[:-1] + ["群内动态（补充）", "更新日期"]


def main(md_path: str, date: str, out_path: str) -> None:
    with open(md_path, encoding="utf-8-sig") as f:
        lines = f.read().splitlines()
    rows = [ln for ln in lines if ln.startswith("|")]
    assert len(rows) >= 3, f"{md_path}: 未找到表格（| 开头行不足 3 行）"
    header = [c.strip() for c in rows[0].strip("|").split("|")]
    assert header == MD_FIELDS, f"表头不符，期望 {MD_FIELDS}，实际 {header}"
    records = []
    for ln in rows[2:]:  # 跳过表头行 + 分隔行
        cells = [c.strip() for c in ln.strip("|").split("|")]
        assert len(cells) == 10, f"行字段数 {len(cells)} != 10: {ln[:80]}"
        rec = dict(zip(RECORD_FIELDS, cells[:-1] + [cells[-1], date]))
        records.append(rec)
    assert records, "表格无数据行"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"create_records": records}, f, ensure_ascii=False)
    print(f"OK: {len(records)} 条 -> {out_path}（更新日期={date}）")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
