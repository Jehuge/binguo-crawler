#!/usr/bin/env python3
"""
合并 comments_*.json 文件为一个 Excel 文件
"""

import json
import os
import glob
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill

# 配置路径
DATA_DIR = os.path.join(os.path.dirname(__file__), "DouyinCrawler", "data")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "merged_comments.xlsx")


def find_json_files():
    """查找所有 comments_*.json 文件"""
    pattern = os.path.join(DATA_DIR, "comments_*.json")
    files = glob.glob(pattern)
    # 按文件名排序
    files.sort()
    return files


def read_comments_file(filepath):
    """读取单个 JSON 文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def main():
    print("开始合并 comments 文件...")
    
    # 获取所有 comments_*.json 文件
    json_files = find_json_files()
    print(f"找到 {len(json_files)} 个 comments 文件")
    
    if not json_files:
        print("未找到任何 comments_*.json 文件")
        return
    
    # 收集所有数据
    all_data = []
    
    # 限制ID范围为1-100
    max_id = min(len(json_files), 100)
    
    for idx, filepath in enumerate(json_files[:max_id], start=1):
        try:
            data = read_comments_file(filepath)
            video_title = data.get('video_title', '')
            comments = data.get('comments', [])
            
            # 从文件名提取视频ID
            filename = os.path.basename(filepath)
            video_id_str = filename.replace('comments_', '').replace('.json', '')
            
            for comment in comments:
                all_data.append({
                    '视频ID': idx,
                    '视频标题': video_title,
                    '评论内容': comment.get('content', ''),
                    '昵称': comment.get('nickname', ''),
                    '地区': comment.get('ip_location', ''),
                    '点赞数': comment.get('like_count', 0),
                    '评论时间': comment.get('create_time_str', ''),
                    '视频ID串': video_id_str
                })
            
            print(f"已处理: {filename}, 包含 {len(comments)} 条评论")
            
        except Exception as e:
            print(f"处理文件 {filepath} 时出错: {e}")
    
    print(f"\n共收集 {len(all_data)} 条评论")
    
    # 创建 DataFrame
    df = pd.DataFrame(all_data)
    
    # 调整列顺序
    columns = ['视频ID', '视频ID串', '视频标题', '评论内容', '昵称', '地区', '点赞数', '评论时间']
    df = df[columns]
    
    # 保存为 Excel
    df.to_excel(OUTPUT_FILE, index=False, engine='openpyxl')
    print(f"\n已保存到: {OUTPUT_FILE}")
    
    # 打印统计信息
    print(f"\n=== 统计信息 ===")
    print(f"视频总数: {df['视频ID'].nunique()}")
    print(f"评论总数: {len(df)}")
    print(f"点赞数最高: {df['点赞数'].max()}")


if __name__ == "__main__":
    main()
