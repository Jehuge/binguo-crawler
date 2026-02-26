# -*- coding: utf-8 -*-
"""
工具函数模块
"""
import json
import os
from datetime import datetime
from pathlib import Path


def ensure_dir(path: str) -> None:
    """确保目录存在"""
    Path(path).mkdir(parents=True, exist_ok=True)


def get_timestamp() -> int:
    """获取当前时间戳（毫秒）"""
    return int(datetime.now().timestamp() * 1000)


def format_time(timestamp: int) -> str:
    """格式化时间戳为可读时间"""
    if not timestamp:
        return ""
    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return ""


def load_json(filepath: str) -> list:
    """加载 JSON 文件"""
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_json(filepath: str, data: list) -> None:
    """保存 JSON 文件"""
    ensure_dir(os.path.dirname(filepath))
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_data_dir() -> str:
    """获取数据存储目录"""
    return "data"


def get_videos_file() -> str:
    """获取视频数据文件路径"""
    return os.path.join(get_data_dir(), "videos.json")


def get_comments_file() -> str:
    """获取评论数据文件路径"""
    return os.path.join(get_data_dir(), "comments.json")
