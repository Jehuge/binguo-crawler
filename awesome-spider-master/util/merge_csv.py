import os
import glob
import pandas as pd

def merge_csv(input_folder="output", output_file="merged.csv"):
    """合并指定文件夹下的所有 CSV 文件"""
    # 找到所有 CSV 文件
    csv_files = glob.glob(os.path.join(input_folder, "*.csv"))
    if not csv_files:
        print("⚠️ 没有找到任何 CSV 文件")
        return

    print(f"🔎 找到 {len(csv_files)} 个 CSV 文件，开始合并...")

    dfs = []
    for file in csv_files:
        try:
            df = pd.read_csv(file, encoding="utf-8-sig")
            dfs.append(df)
            print(f"✅ 已读取 {file}，包含 {len(df)} 行")
        except Exception as e:
            print(f"❌ 读取 {file} 失败: {e}")

    if not dfs:
        print("⚠️ 没有可用的数据")
        return

    # 合并所有 CSV
    merged_df = pd.concat(dfs, ignore_index=True)

    # 去重（按 url 去重，保留第一条）
    if "url" in merged_df.columns:
        merged_df.drop_duplicates(subset=["url"], inplace=True)

    # 保存结果
    merged_df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"✅ 合并完成，共 {len(merged_df)} 条记录，已保存到 {output_file}")

if __name__ == "__main__":
    merge_csv(input_folder="output", output_file="merged.csv")