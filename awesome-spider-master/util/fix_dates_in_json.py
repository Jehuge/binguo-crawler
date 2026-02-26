import json
import re
from datetime import datetime

def fix_dates_in_json(input_file: str, output_file: str, year: int = 2025):
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        date_str = item.get("date", "")
        # 匹配 "MM-DD" 格式
        if re.match(r"^\d{2}-\d{2}$", date_str):
            try:
                fixed_date = datetime.strptime(f"{year}-{date_str}", "%Y-%m-%d")
                item["date"] = fixed_date.strftime("%Y-%m-%d")
            except ValueError:
                # 日期不合法时跳过
                pass

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"✅ 日期修复完成: {input_file} → {output_file}")


if __name__ == "__main__":
    # 用法：修改 "your.json" 为你的 JSON 文件
    fix_dates_in_json("your.json", "your_fixed.json", year=2025)