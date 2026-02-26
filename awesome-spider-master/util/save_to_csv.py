import csv
import os

def save_to_csv(records, filename="output/results.csv"):
    """保存结果到 CSV"""
    if not records:
        print("⚠️ 没有数据，不保存")
        return

    os.makedirs(os.path.dirname(filename), exist_ok=True)
    mode = 'a' if os.path.exists(filename) else 'w'

    fieldnames = ["site_name", "advertiser", "date", "title", "url"]

    with open(filename, mode, newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if mode == 'w':
            writer.writeheader()
        writer.writerows(records)

    print(f"✅ 保存 {len(records)} 条数据到 {filename}")