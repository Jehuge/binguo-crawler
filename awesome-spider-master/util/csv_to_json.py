import csv
import json
import sys
import os


def csv_to_json(csv_file: str, json_file: str = None, encoding: str = "utf-8") -> None:
    """
    将 CSV 文件转换为 JSON 文件
    :param csv_file: 输入的 CSV 文件路径
    :param json_file: 输出的 JSON 文件路径（默认与输入同名）
    :param encoding: 文件编码，默认 utf-8
    """
    if not os.path.exists(csv_file):
        raise FileNotFoundError(f"❌ 文件不存在: {csv_file}")

    if json_file is None:
        json_file = os.path.splitext(csv_file)[0] + ".json"

    with open(csv_file, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=4)

    print(f"✅ 转换完成: {csv_file} → {json_file} (共 {len(rows)} 条)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python csv_to_json.py input.csv [output.json]")
        sys.exit(1)

    csv_file = sys.argv[1]
    json_file = sys.argv[2] if len(sys.argv) > 2 else None

    csv_to_json(csv_file, json_file)