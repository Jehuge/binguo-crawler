# -*- coding: utf-8 -*-
"""
数据存储模块
"""
import os
import time
from typing import Any, Dict, List
from utils import ensure_dir, load_json, save_json, get_videos_file, get_comments_file


class DataStore:
    """数据存储类"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        ensure_dir(data_dir)
    
    def _format_time(self, timestamp: int) -> str:
        """格式化时间"""
        if not timestamp:
            return "-"
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        except:
            return "-"
    
    def _transform_comment(self, comment: Dict, video_title: str = "") -> Dict:
        """转换评论数据格式以适配前端"""
        user = comment.get("user", {})
        return {
            "aweme_id": comment.get("aweme_id", ""),
            "cid": comment.get("cid", ""),
            "video_title": video_title,
            "content": comment.get("text", ""),
            "nickname": user.get("nickname", "-"),
            "avatar": user.get("avatar_thumb", {}).get("url_list", [""])[0] if user.get("avatar_thumb") else "",
            "like_count": comment.get("digg_count", 0),
            "create_time": comment.get("create_time", 0),
            "create_time_str": self._format_time(comment.get("create_time", 0)),
            "ip_location": comment.get("ip_label", ""),  # 评论用户地区
        }
    
    def _transform_video(self, video: Dict) -> Dict:
        """转换视频数据格式以适配前端"""
        return {
            "aweme_id": video.get("aweme_id", ""),
            "title": video.get("desc", ""),
            "nickname": video.get("author", {}).get("nickname", "-") if video.get("author") else "-",
            "avatar": video.get("author", {}).get("avatar", {}).get("url_list", [""])[0] if video.get("author") and video.get("author").get("avatar") else "",
            "cover_url": video.get("video", {}).get("cover", {}).get("url_list", [""])[0] if video.get("video") and video.get("video").get("cover") else "",
            "liked_count": video.get("statistics", {}).get("digg_count", 0),
            "liked_count_str": self._format_count(video.get("statistics", {}).get("digg_count", 0)),
            "comment_count": video.get("statistics", {}).get("comment_count", 0),
            "comment_count_str": self._format_count(video.get("statistics", {}).get("comment_count", 0)),
            "create_time": video.get("create_time", 0),
            "create_time_str": self._format_time(video.get("create_time", 0)),
        }
    
    def _format_count(self, count: int) -> str:
        """格式化数量显示"""
        if count >= 100000000:
            return f"{count / 100000000:.1f}亿"
        elif count >= 10000:
            return f"{count / 10000:.1f}万"
        else:
            return str(count)
    
    def save_videos(self, videos: List[Dict]) -> str:
        """保存视频数据"""
        filepath = os.path.join(self.data_dir, "videos.json")
        save_json(filepath, videos)
        return filepath
    
    def load_videos(self) -> List[Dict]:
        """加载视频数据"""
        filepath = os.path.join(self.data_dir, "videos.json")
        raw_videos = load_json(filepath)
        # 转换格式
        return [self._transform_video(v) for v in raw_videos] if raw_videos else []
    
    def save_comments(self, comments: List[Dict], video_id: str = None, video_title: str = "") -> str:
        """保存评论数据 (新的扁平结构)"""
        if video_id:
            filename = f"comments_{video_id}.json"
        else:
            filename = "comments.json"
        filepath = os.path.join(self.data_dir, filename)
        
        # 统一为新的结构： { "video_title": "...", "comments": [ ... ] }
        output_data = {
            "video_title": video_title,
            "comments": comments
        }
        
        save_json(filepath, output_data)
        return filepath
    
    def load_comments(self, video_id: str = None) -> List[Dict]:
        """加载评论数据"""
        if video_id:
            filename = f"comments_{video_id}.json"
        else:
            filename = "comments.json"
        filepath = os.path.join(self.data_dir, filename)
        raw_data = load_json(filepath)
        
        if not raw_data:
            return []
            
        video_title = ""
        # 兼容旧版本格式 (如果直接是一个列表)
        if isinstance(raw_data, list):
            raw_comments = raw_data
        # 新版本格式 dict
        elif isinstance(raw_data, dict):
            video_title = raw_data.get("video_title", "")
            raw_comments = raw_data.get("comments", [])
        else:
            return []
            
        # 针对新格式，组装回给前端的统一格式
        transformed = []
        for c in raw_comments:
            if "video_title" not in c and video_title:
                c["video_title"] = video_title
            transformed.append(c)
            
        return transformed
    
    def get_videos_by_ids(self, aweme_ids: List[str]) -> List[Dict]:
        """根据 ID 列表获取视频"""
        videos = self.load_videos()
        return [v for v in videos if v.get("aweme_id") in aweme_ids]
    
    def get_comments_by_video_ids(self, aweme_ids: List[str]) -> List[Dict]:
        """根据视频 ID 列表获取评论"""
        comments = self.load_comments()
        return [c for c in comments if c.get("aweme_id") in aweme_ids]
    
    def clear_data(self) -> None:
        """清空数据"""
        videos_file = os.path.join(self.data_dir, "videos.json")
        
        if os.path.exists(videos_file):
            os.remove(videos_file)
            
        for file in os.listdir(self.data_dir):
            if file.startswith("comments") and file.endswith(".json"):
                os.remove(os.path.join(self.data_dir, file))
    
    def get_export_path(self, data_type: str = "all") -> str:
        """获取导出文件路径"""
        import shutil
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = os.path.join(self.data_dir, "exports")
        ensure_dir(export_dir)
        
        if data_type == "all":
            # 创建包含视频和评论的压缩文件
            import zipfile
            zip_path = os.path.join(export_dir, f"douyin_data_{timestamp}.zip")
            with zipfile.ZipFile(zip_path, 'w') as zf:
                videos_file = os.path.join(self.data_dir, "videos.json")
                if os.path.exists(videos_file):
                    zf.write(videos_file, "videos.json")
                    
                for file in os.listdir(self.data_dir):
                    if file.startswith("comments") and file.endswith(".json"):
                        zf.write(os.path.join(self.data_dir, file), file)
            return zip_path
        elif data_type == "videos":
            # 复制视频文件
            src = os.path.join(self.data_dir, "videos.json")
            dst = os.path.join(export_dir, f"videos_{timestamp}.json")
            if os.path.exists(src):
                shutil.copy(src, dst)
                return dst
        elif data_type == "comments":
            import zipfile
            zip_path = os.path.join(export_dir, f"douyin_comments_{timestamp}.zip")
            with zipfile.ZipFile(zip_path, 'w') as zf:
                for file in os.listdir(self.data_dir):
                    if file.startswith("comments") and file.endswith(".json"):
                        zf.write(os.path.join(self.data_dir, file), file)
            return zip_path
        return ""


# 全局数据存储实例
data_store = DataStore()
