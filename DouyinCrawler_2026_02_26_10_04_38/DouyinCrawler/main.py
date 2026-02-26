# -*- coding: utf-8 -*-
"""
FastAPI 应用主文件
"""
import asyncio
import json
import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import config
from crawler import DouYinCrawler
from data_store import DataStore
from utils import format_time

# 创建 FastAPI 应用
app = FastAPI(
    title="抖音爬虫 API",
    description="抖音视频评论爬取工具",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局变量
crawler: Optional[DouYinCrawler] = None
data_store = DataStore(config.DATA_DIR)


# ============ 数据模型 ============

class SearchRequest(BaseModel):
    keyword: str
    sort_type: int = 0  # 0: 综合, 1: 点赞最多, 2: 最新
    publish_time: int = 0  # 0: 不限, 1: 一天内, 7: 一周内, 180: 半年内
    max_count: int = 100  # 最大视频数量


class CrawlRequest(BaseModel):
    video_ids: List[str]
    max_comments: int = config.CRAWLER_MAX_COMMENTS_COUNT  # 默认使用配置中的单视频最大评论数
    delay: float = config.CRAWLER_MAX_SLEEP_SEC  # 默认使用配置中的请求间隔


# ============ API 路由 ============

@app.get("/")
async def root():
    """返回主页"""
    # 返回 HTML 页面
    import os
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    return FileResponse(template_path)


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "crawler_ready": crawler is not None}


# ============ 登录相关 ============

@app.get("/api/login/status")
async def get_login_status():
    """获取登录状态"""
    global crawler
    
    if crawler is None:
        return {
            "logged_in": False,
            "message": "爬虫未启动"
        }
    
    try:
        is_logged_in = await crawler.is_logged_in()
        return {
            "logged_in": is_logged_in,
            "message": "已登录" if is_logged_in else "请扫码登录"
        }
    except Exception as e:
        return {
            "logged_in": False,
            "message": str(e)
        }


@app.post("/api/login/start")
async def start_login():
    """启动登录流程"""
    global crawler
    
    # 如果已有爬虫实例且已登录，直接返回
    if crawler is not None:
        try:
            if await crawler.is_logged_in():
                return {"success": True, "message": "已经登录"}
        except:
            pass
    
    try:
        # 创建新的爬虫实例（不等待登录完成）
        crawler = DouYinCrawler()
        
        # 在后台运行爬虫启动（包括登录）
        asyncio.create_task(crawler.start())
        
        return {"success": True, "message": "请扫码登录抖音，浏览器已打开"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/login/check")
async def check_login():
    """检查登录状态（轮询用）"""
    global crawler
    
    if crawler is None:
        return {"logged_in": False, "message": "爬虫未启动"}
    
    try:
        is_logged_in = await crawler.is_logged_in()
        return {
            "logged_in": is_logged_in,
            "message": "已登录" if is_logged_in else "请扫码登录"
        }
    except Exception as e:
        return {"logged_in": False, "message": str(e)}


# ============ 搜索相关 ============

@app.post("/api/search")
async def search_videos(request: SearchRequest):
    """搜索视频"""
    global crawler
    
    if crawler is None:
        return {"success": False, "detail": "请先登录"}
    
    try:
        videos = await crawler.search_videos(
            keyword=request.keyword,
            sort_type=request.sort_type,
            publish_time=request.publish_time,
            max_count=request.max_count,
        )
        return {
            "success": True,
            "videos": videos,
            "total": len(videos)
        }
    except Exception as e:
        return {"success": False, "detail": str(e)}


@app.post("/api/crawl")
async def crawl_comments(request: CrawlRequest):
    """爬取评论"""
    global crawler
    
    if crawler is None:
        return {"success": False, "detail": "请先登录"}
    
    try:
        # 启动爬取任务
        # 先调用 progress.start 初始化进度状态
        crawler.progress.start(request.keyword if hasattr(request, 'keyword') else "", request.video_ids)
        
        crawl_task = asyncio.create_task(
            crawler.crawl_comments(
                video_ids=request.video_ids,
                max_comments=request.max_comments,
                delay=request.delay,
            )
        )
        
        # 等待一小段时间让爬虫开始
        await asyncio.sleep(1)
        
        return {
            "success": True,
            "message": f"开始爬取 {len(request.video_ids)} 个视频，间隔 {request.delay} 秒"
        }
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"爬取评论失败: {error_msg}")
        return {"success": False, "detail": str(e)}


@app.get("/api/crawl/progress")
async def get_crawl_progress():
    """获取爬取进度"""
    global crawler
    if crawler is None or crawler.progress is None:
        return {"success": False, "detail": "未启动爬虫"}
    
    try:
        status = crawler.progress.get_status()
        return {"success": True, "data": status}
    except Exception as e:
        return {"success": False, "detail": str(e)}


@app.post("/api/crawl/stop")
async def stop_crawl():
    """停止爬取"""
    global crawler
    if crawler and crawler.progress:
        crawler.progress.request_stop()
        return {"success": True, "message": "正在停止爬取..."}
    return {"success": False, "detail": "没有正在进行的爬取"}


@app.post("/api/crawl/continue")
async def continue_crawl():
    """继续爬取(断点续传)"""
    global crawler
    
    if crawler is None:
        return {"success": False, "detail": "请先登录"}
    
    try:
        remaining = crawler.progress.get_remaining_ids()
        if not remaining:
            return {"success": False, "detail": "没有剩余视频，已全部爬取完成"}
        
        delay = config.CRAWLER_MAX_SLEEP_SEC  # 使用配置中的延迟
        
        # 启动继续爬取任务
        crawl_task = asyncio.create_task(
            crawler.crawl_comments(
                video_ids=remaining,
                max_comments=config.CRAWLER_MAX_COMMENTS_COUNT,
                delay=delay
            )
        )
        
        return {
            "success": True,
            "message": f"继续爬取剩余 {len(remaining)} 个视频"
        }
    except Exception as e:
        return {"success": False, "detail": str(e)}


# ============ 数据相关 ============

@app.get("/api/data/videos")
async def get_videos():
    """获取视频数据"""
    try:
        videos = data_store.load_videos()
        return {"success": True, "data": videos, "total": len(videos)}
    except Exception as e:
        return {"success": False, "detail": str(e)}


@app.get("/api/data/comments")
async def get_comments():
    """获取评论数据"""
    try:
        # 获取所有分文件的评论
        all_comments = []
        for file in os.listdir(data_store.data_dir):
            if file.startswith("comments") and file.endswith(".json"):
                vid = file.replace("comments_", "").replace(".json", "")
                if vid == "comments":
                    vid = None
                all_comments.extend(data_store.load_comments(video_id=vid))
        return {"success": True, "data": all_comments, "total": len(all_comments)}
    except Exception as e:
        return {"success": False, "detail": str(e)}


@app.get("/api/data/preview")
async def preview_data(data_type: str = "videos", limit: int = 50):
    """预览数据"""
    try:
        if data_type == "videos":
            data = data_store.load_videos()[:limit]
        else:
            # 简单拼接一下用于预览
            all_comments = []
            for file in os.listdir(data_store.data_dir):
                if file.startswith("comments") and file.endswith(".json"):
                    vid = file.replace("comments_", "").replace(".json", "")
                    if vid == "comments":
                        vid = None
                    all_comments.extend(data_store.load_comments(video_id=vid))
                    if len(all_comments) >= limit:
                        break
            data = all_comments[:limit]
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "detail": str(e)}


@app.get("/api/data/download")
async def download_data(data_type: str = "all"):
    """下载数据"""
    try:
        if data_type == "all" or data_type == "videos":
            videos = data_store.load_videos()
            data_store.save_videos(videos)
        
        if data_type == "all" or data_type == "comments":
            comments = data_store.load_comments()
            data_store.save_comments(comments)
        
        file_path = data_store.get_export_path(data_type)
        
        if not os.path.exists(file_path):
            return {"success": False, "detail": "没有可下载的数据"}
        
        return FileResponse(
            file_path,
            media_type='application/octet-stream',
            filename=os.path.basename(file_path)
        )
    except Exception as e:
        return {"success": False, "detail": str(e)}


@app.delete("/api/data/clear")
async def clear_data():
    """清空数据"""
    try:
        await data_store.clear_all()
        return {"success": True, "message": "数据已清空"}
    except Exception as e:
        return {"success": False, "detail": str(e)}


# ============ 启动应用 ============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
