# -*- coding: utf-8 -*-
"""
抖音爬虫核心类
"""
import asyncio
import json
import os
import time
from typing import List, Dict, Any, Optional, Callable

import httpx
from playwright.async_api import async_playwright, BrowserContext, Page, Playwright
from pydantic import BaseModel

import config
from douyin_client import DouYinClient
from data_store import DataStore


def _get_random_sleep(min_sec: float, max_sec: float, use_jitter: bool = True, jitter_ratio: float = 0.3) -> float:
    """生成随机睡眠时间
    
    Args:
        min_sec: 最小睡眠时间
        max_sec: 最大睡眠时间
        use_jitter: 是否使用抖动
        jitter_ratio: 抖动比例
    
    Returns:
        睡眠时间（秒）
    """
    # 使用时间戳的小数部分作为伪随机数
    base = min_sec + (max_sec - min_sec) * (time.time() % 1)
    if use_jitter:
        jitter = base * jitter_ratio * ((time.time() * 1000000) % 100 / 100 - 0.5) * 2
        base = max(0.5, base + jitter)
    return base


class CrawlProgress:
    """爬取进度跟踪"""
    
    def __init__(self, state_file: str = "data/crawl_state.json"):
        self.state_file = state_file
        self.state = {
            "is_running": False,
            "is_stopping": False,  # 停止标志
            "keyword": "",
            "video_ids": [],
            "completed_ids": [],
            "current_video_id": "",
            "current_video_title": "",
            "current_video_comment_count": 0,
            "current_video_cursor": 0,  # 记录当前视频爬取到的主评论游标，以便断点续传
            "total_videos": 0,
            "total_comments": 0,
            "failed_ids": [],
            "start_time": 0,
            "last_update": 0,
        }
        self._load()
        
        # 如果不是我们发起的停止，仅仅是重启/刷新，应当允许继续
        if self.state.get("is_running", False):
            # 将 is_running 置为 false 以允许从前端重新点继续，但保留所有其它断点状态
            self.state["is_running"] = False
            self.state["is_stopping"] = False
            self._save()
    
    def request_stop(self):
        """请求停止爬取"""
        self.state["is_stopping"] = True
        self._save()
    
    def is_stop_requested(self) -> bool:
        """检查是否请求停止"""
        return self.state.get("is_stopping", False)
    
    def _load(self):
        """加载状态"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
            except:
                pass
    
    def _save(self):
        """保存状态"""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        self.state["last_update"] = int(time.time())
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
    
    def start(self, keyword: str, video_ids: List[str]):
        """开始爬取"""
        self.state["is_running"] = True
        self.state["is_stopping"] = False
        self.state["keyword"] = keyword
        self.state["video_ids"] = video_ids
        self.state["completed_ids"] = []
        self.state["failed_ids"] = []
        self.state["current_video_id"] = ""
        self.state["current_video_title"] = ""
        self.state["current_video_comment_count"] = 0
        self.state["current_video_cursor"] = 0
        self.state["total_videos"] = len(video_ids)
        self.state["total_comments"] = 0
        self.state["start_time"] = int(time.time())
        self._save()
    
    def update_progress(self, video_id: str, video_title: str, comment_count: int, cursor: int = 0):
        """更新进度"""
        self.state["current_video_id"] = video_id
        self.state["current_video_title"] = video_title[:30] if video_title else ""
        
        # 因为我们是在单视频内不断增加 comment_count 的，所以要先减去之前的再加上最新的，保持总数正确
        old_count = self.state.get("current_video_comment_count", 0)
        self.state["total_comments"] += (comment_count - old_count)
        
        self.state["current_video_comment_count"] = comment_count
        self.state["current_video_cursor"] = cursor
        
        # 仅当传入特殊标识或外界完成时才加入 completed_ids，这在 crawler.py 里会处理
        self._save()

    def mark_completed(self, video_id: str):
        """标记视频完成"""
        if video_id not in self.state["completed_ids"]:
            self.state["completed_ids"].append(video_id)
        if video_id in self.state["failed_ids"]:
            self.state["failed_ids"].remove(video_id)
        self.state["current_video_cursor"] = 0  # 重置游标
        self.state["current_video_comment_count"] = 0
        self._save()
    
    def mark_failed(self, video_id: str):
        """标记失败的视频"""
        if video_id not in self.state["failed_ids"]:
            self.state["failed_ids"].append(video_id)
        self._save()
    
    def finish(self):
        """完成爬取"""
        self.state["is_running"] = False
        self.state["is_stopping"] = False
        self.state["current_video_id"] = ""
        self.state["current_video_title"] = ""
        self._save()
    
    def get_remaining_ids(self) -> List[str]:
        """获取剩余未爬取的视频ID"""
        return [vid for vid in self.state["video_ids"] 
                if vid not in self.state["completed_ids"] and vid not in self.state["failed_ids"]]
    
    def get_status(self) -> Dict:
        """获取状态"""
        return {
            "is_running": self.state["is_running"],
            "keyword": self.state["keyword"],
            "total_videos": self.state["total_videos"],
            "completed_count": len(self.state["completed_ids"]),
            "failed_count": len(self.state["failed_ids"]),
            "current_video_id": self.state["current_video_id"],
            "current_video_title": self.state["current_video_title"],
            "current_video_comment_count": self.state.get("current_video_comment_count", 0),
            "total_comments": self.state["total_comments"],
            "progress_percent": round(len(self.state["completed_ids"]) / max(1, self.state["total_videos"]) * 100, 1),
            "remaining_ids": self.get_remaining_ids(),
        }


class DouYinCrawler:
    """抖音爬虫类"""
    
    index_url = "https://www.douyin.com"
    
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser_context: Optional[BrowserContext] = None
        self.context_page: Optional[Page] = None
        self.dy_client: Optional[DouYinClient] = None
        self._logged_in = False
        self.data_store = DataStore(config.DATA_DIR)
        self.progress = CrawlProgress()
        self._progress_callback: Optional[Callable] = None
    
    def set_progress_callback(self, callback: Callable):
        """设置进度回调"""
        self._progress_callback = callback
    
    async def start(self) -> None:
        """启动爬虫并等待登录"""
        # 启动 Playwright
        self.playwright = await async_playwright().start()
        
        # 检查是否启用 CDP 模式
        if getattr(config, 'ENABLE_CDP_MODE', False):
            await self._start_cdp_mode()
        else:
            await self._start_normal_mode()
        
        # 创建抖音客户端
        self.dy_client = await self._create_douyin_client()
    
    async def _detect_browser_path(self) -> Optional[str]:
        """检测已安装的浏览器路径"""
        import shutil
        
        # 尝试检测 Chrome
        chrome_path = shutil.which("google-chrome") or shutil.which("chrome")
        if chrome_path:
            return chrome_path
        
        # 尝试检测 Edge
        edge_path = shutil.which("microsoft-edge") or shutil.which("msedge")
        if edge_path:
            return edge_path
        
        # macOS 常见路径
        macos_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
        for path in macos_paths:
            if os.path.exists(path):
                return path
        
        # Windows 常见路径
        windows_paths = [
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
        ]
        for path in windows_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    async def _start_cdp_mode(self) -> None:
        """使用 CDP 模式启动浏览器（使用真实浏览器）"""
        import subprocess
        import socket
        
        # 检测或使用自定义浏览器路径
        browser_path = getattr(config, 'CUSTOM_BROWSER_PATH', "") or await self._detect_browser_path()
        if not browser_path:
            print("⚠️ 未找到已安装的 Chrome/Edge 浏览器，回退到普通模式")
            await self._start_normal_mode()
            return
        
        print(f"使用 CDP 模式，浏览器路径: {browser_path}")
        
        # 查找可用端口
        def find_available_port(start_port: int) -> int:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                for port in range(start_port, start_port + 100):
                    try:
                        s.bind(('127.0.0.1', port))
                        return port
                    except OSError:
                        continue
            return start_port
        
        debug_port = getattr(config, 'CDP_DEBUG_PORT', 9222)
        debug_port = find_available_port(debug_port)
        
        # 启动浏览器
        user_data_dir = os.path.join(os.getcwd(), config.USER_DATA_DIR) if config.SAVE_LOGIN_STATE else None
        
        # 构建浏览器启动参数
        browser_args = [
            f"--remote-debugging-port={debug_port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-component-extensions-with-background-pages",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-sync",
            "--metrics-recording-only",
            "--no-crash-upload",
        ]
        
        # macOS specific
        import platform
        if platform.system() == "Darwin":
            browser_args.extend([
                "--no-sandbox",
            ])
        
        if user_data_dir:
            browser_args.append(f"--user-data-dir={user_data_dir}")
        
        if getattr(config, 'CDP_HEADLESS', False):
            browser_args.append("--headless=new")
        
        print(f"启动浏览器: {browser_path} {' '.join(browser_args)}")
        
        # 先尝试连接到已存在的浏览器（如果有）
        cdp_url = f"http://127.0.0.1:{debug_port}/json"
        browser = None
        
        try:
            # 尝试连接到已存在的调试端口浏览器
            async with httpx.AsyncClient() as client:
                resp = await client.get(cdp_url, timeout=2)
                if resp.status_code == 200:
                    ws_endpoint = resp.json()[0]["webSocketDebuggerUrl"]
                    browser = await self.playwright.chromium.connect_over_cdp(ws_endpoint)
                    print("✅ 连接到已存在的浏览器")
        except Exception:
            pass
        
        if browser is None:
            # 启动新浏览器
            launch_options = {
                "executable_path": browser_path,
                "args": browser_args,
                "headless": getattr(config, 'CDP_HEADLESS', False),
            }
            try:
                browser = await self.playwright.chromium.launch(**launch_options)
                print("✅ 新浏览器启动成功")
            except Exception as e:
                print(f"⚠️ 启动 Chrome 失败: {e}")
                print("回退到普通模式...")
                await self._start_normal_mode()
                return
        
        # 获取或创建上下文
        contexts = browser.contexts
        if contexts:
            self.browser_context = contexts[0]
        else:
            self.browser_context = await browser.new_context()
        
        # 创建新页面
        self.context_page = await self.browser_context.new_page()
        
        # 导航到抖音
        await self.context_page.goto(self.index_url)
        
        # 等待用户扫码登录
        print("请扫码登录抖音...")
        await self.wait_for_login()
        
        print("登录成功!")
        self._logged_in = True
    
    async def _start_normal_mode(self) -> None:
        """普通模式启动浏览器"""
        # 启动浏览器
        chromium = self.playwright.chromium
        user_data_dir = os.path.join(os.getcwd(), config.USER_DATA_DIR) if config.SAVE_LOGIN_STATE else None
        
        # 添加反检测参数
        launch_args = [
            "--window-size=1280,800",
            "--window-position=100,100",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-component-extensions-with-background-pages",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-sync",
            "--metrics-recording-only",
            "--no-crash-upload",
        ]
        
        # macOS specific
        import platform
        if platform.system() == "Darwin":
            launch_args.append("--no-sandbox")
        
        self.browser_context = await chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            accept_downloads=True,
            headless=config.HEADLESS,
            viewport={"width": 1280, "height": 800},
            args=launch_args,
        )
        
        # 创建新页面
        self.context_page = await self.browser_context.new_page()
        
        # 注入反检测脚本 - 覆盖 webdriver 属性
        await self.context_page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
            window.chrome = { runtime: {} };
        """)
        
        await self.context_page.goto(self.index_url)
        
        # 等待用户扫码登录
        print("请扫码登录抖音...")
        await self.wait_for_login()
        
        print("登录成功!")
        self._logged_in = True
    
    async def _create_douyin_client(self) -> "DouYinClient":
        """创建抖音客户端"""
        # 获取 cookies
        cookies = await self.browser_context.cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
        # 获取 User-Agent
        user_agent = await self.context_page.evaluate("() => navigator.userAgent")
        
        douyin_client = DouYinClient(
            headers={
                "User-Agent": user_agent,
                "Cookie": cookie_str, 
                "Host": "www.douyin.com",
                "Origin": "https://www.douyin.com/",
                "Referer": "https://www.douyin.com/",
                "Content-Type": "application/json;charset=UTF-8",
            },
            playwright_page=self.context_page,
            browser_context=self.browser_context,
        )
        return douyin_client
    
    async def is_logged_in(self) -> bool:
        """检查是否已登录"""
        if self._logged_in:
            return True
        
        if self.context_page is None:
            return False
        
        try:
            local_storage = await self.context_page.evaluate("() => window.localStorage")
            if local_storage.get("HasUserLogin", "") == "1":
                self._logged_in = True
                return True
            
            cookies = await self.browser_context.cookies()
            cookie_dict = {c["name"]: c["value"] for c in cookies}
            if cookie_dict.get("LOGIN_STATUS") == "1":
                self._logged_in = True
                return True
        except Exception:
            pass
        
        return False
    
    async def wait_for_login(self, timeout: int = 300) -> None:
        """等待用户扫码登录"""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if await self.is_logged_in():
                return
            await asyncio.sleep(2)
        
        raise TimeoutError("登录超时")
    
    async def search_videos(
        self,
        keyword: str,
        sort_type: int = 0,
        publish_time: int = 0,
        max_count: int = 20,
    ) -> List[Dict[str, Any]]:
        """搜索视频"""
        if self.dy_client is None:
            self.dy_client = await self._create_douyin_client()
        
        videos = []
        page = 0
        videos_per_page = 15
        search_id = ""
        
        # 分页获取直到达到最大数量
        while len(videos) < max_count:
            # 添加延迟避免风控（使用随机抖动）
            if page > 0:
                sleep_time = _get_random_sleep(
                    config.CRAWLER_MIN_SLEEP_SEC,
                    config.CRAWLER_MAX_SLEEP_SEC,
                    config.CRAWLER_USE_JITTER,
                    config.CRAWLER_JITTER_RATIO
                )
                await asyncio.sleep(sleep_time)
            
            result = await self.dy_client.search_videos(
                keyword=keyword,
                sort_type=sort_type,
                publish_time=publish_time,
                offset=page * videos_per_page,
                search_id=search_id,
            )
            
            # 解析搜索结果，与 MediaCrawler 保持一致
            data = result.get("data", [])
            
            if not data:
                # 可能是因为翻页完毕，或者风控导致没数据，稍微打印个日志
                print(f"搜索到底或无数据返回, 已获取 {len(videos)} 个视频")
                break
            
            search_id = result.get("extra", {}).get("logid", "")
            
            for post_item in data:
                try:
                    aweme_info = post_item.get("aweme_info") or post_item.get("aweme_mix_info", {}).get("mix_items", [{}])[0]
                except (TypeError, IndexError):
                    continue
                
                if not aweme_info:
                    continue
                
                # 提取需要的信息
                video = {
                    "aweme_id": aweme_info.get("aweme_id", ""),
                    "title": aweme_info.get("desc", ""),
                    "cover_url": aweme_info.get("video", {}).get("cover", {}).get("url_list", [""])[0] if aweme_info.get("video") else "",
                    "nickname": aweme_info.get("author", {}).get("nickname", ""),
                    "avatar": aweme_info.get("author", {}).get("avatar", {}).get("url_list", [""])[0] if aweme_info.get("author") else "",
                    "liked_count_str": self._format_count(aweme_info.get("statistics", {}).get("digg_count", 0)),
                    "comment_count_str": self._format_count(aweme_info.get("statistics", {}).get("comment_count", 0)),
                    "create_time": aweme_info.get("create_time", 0),
                }
                videos.append(video)
                
                if len(videos) >= max_count:
                    break
            
            page += 1
        
        return videos[:max_count]
    
    def _format_timestamp(self, timestamp: int) -> str:
        """格式化时间戳"""
        if not timestamp:
            return ""
        time_local = time.localtime(timestamp)
        return time.strftime("%Y-%m-%d %H:%M:%S", time_local)

    def _format_count(self, count: int) -> str:
        """格式化数量显示"""
        if count >= 100000000:
            return f"{count / 100000000:.1f}亿"
        elif count >= 10000:
            return f"{count / 10000:.1f}万"
        else:
            return str(count)
    
    async def crawl_comments(
        self,
        video_ids: List[str],
        max_comments: int = 0,
        delay: float = 3.0,
    ) -> Dict[str, Any]:
        """爬取评论
        
        Args:
            video_ids: 视频ID列表
            max_comments: 每个视频最多爬取评论数，0表示全部
            delay: 请求间隔(秒)，建议3-5秒防封
        """
        if self.dy_client is None:
            self.dy_client = await self._create_douyin_client()
        
        all_comments = []
        all_videos = []
        
        # 获取已完成的ID列表用于断点续传
        completed_ids = set(self.progress.state.get("completed_ids", []))
        # 不过滤 failed_ids，因为 failed_ids 就是我们要断点续传的对象
        
        # 过滤掉已完成的视频
        remaining_ids = [vid for vid in video_ids if vid not in completed_ids]
        
        print(f"开始爬取评论，共 {len(video_ids)} 个视频，已完成 {len(completed_ids)} 个，剩余 {len(remaining_ids)} 个")
        
        for i, video_id in enumerate(remaining_ids):
            # 获取该视频的断点游标
            start_cursor = 0
            if video_id == self.progress.state.get("current_video_id") and video_id in self.progress.state.get("failed_ids", []):
                start_cursor = self.progress.state.get("current_video_cursor", 0)
                print(f"发现中断记录，视频 {video_id} 从游标 {start_cursor} 处继续爬取...")
            # 检查是否请求停止
            if self.progress.is_stop_requested():
                print("收到停止请求，正在停止爬取...")
                self.progress.finish()
                break
            
            try:
                current_title = ""
                print(f"[{i+1}/{len(remaining_ids)}] 正在获取视频 {video_id} 的详情...")
                
                # 获取视频详情
                video_info = await self.dy_client.get_video_detail(video_id)
                if video_info:
                    all_videos.append(video_info)
                    current_title = video_info.get("desc", "")[:50]
                    print(f"视频详情获取成功: {current_title}...")
                    # 实时保存视频信息
                    existing_videos = self.data_store.load_videos()
                    existing_video_ids = {v.get("aweme_id", "") for v in existing_videos}
                    if video_info.get("aweme_id", "") not in existing_video_ids:
                        self.data_store.save_videos(existing_videos + [video_info])
                
                # 如果不是从0开始，意味着我们在继续，不能把原本的数量重置为0，保留原来的
                init_count = self.progress.state.get("current_video_comment_count", 0) if start_cursor > 0 else 0
                
                # 更新初始进度
                self.progress.update_progress(video_id, current_title, init_count, start_cursor)
                if self._progress_callback:
                    self._progress_callback(self.progress.get_status())
                
                comment_count = 0
                comments = []
                
                # 定义内部进度回调
                def on_comment_progress(current_fetched: int, current_cursor: int):
                    self.progress.update_progress(video_id, current_title, init_count + current_fetched, current_cursor)
                    if self._progress_callback:
                        self._progress_callback(self.progress.get_status())
                        
                max_count = max_comments if max_comments > 0 else 5000
                # 如果是断点续传，需要扣除已经爬取的数量
                remaining_count_for_video = max_count - init_count
                
                if remaining_count_for_video > 0:
                    comments = await self.dy_client.get_all_comments(
                        video_id, 
                        max_count=remaining_count_for_video, 
                        progress_callback=on_comment_progress,
                        start_cursor=start_cursor
                    )
                
                # 过滤垃圾字段，只保留有价值字段，并过滤掉空数据
                filtered_comments = []
                for c in comments:
                    cid = c.get("cid", "")
                    text = c.get("text", "")
                    
                    # 过滤掉空的 cid 或 空内容的评论
                    if not cid or not text:
                        continue
                        
                    # 只保留最核心的几个字段，video_title 提到外层，不再每条重复
                    filtered_c = {
                        "cid": cid,
                        "aweme_id": c.get("aweme_id", ""),
                        "content": text,
                        "nickname": c.get("user", {}).get("nickname", ""),
                        "like_count": c.get("digg_count", 0),
                        "create_time_str": self._format_timestamp(c.get("create_time", 0)),
                        "ip_location": c.get("ip_label", ""),  # 评论用户地区
                    }
                    filtered_comments.append(filtered_c)

                comment_count = len(filtered_comments)
                all_comments.extend(filtered_comments)
                print(f"获取到 {comment_count} 条评论")
                
                # 实时保存评论到文件 (按视频 ID 分开)
                if filtered_comments:
                    existing_comments = self.data_store.load_comments(video_id=video_id)
                    
                    # 去重，因为只有核心字段，所以我们把 content 作为去重标识（可选）或者简单合并
                    # 这里如果是基于新格式，直接用 text 简单去重
                    existing_texts = {c.get("content", "") for c in existing_comments}
                    new_comments = [c for c in filtered_comments if c.get("content", "") not in existing_texts]
                    
                    if new_comments:
                        self.data_store.save_comments(
                            existing_comments + new_comments, 
                            video_id=video_id, 
                            video_title=current_title
                        )
                        print(f"已实时保存 {len(new_comments)} 条新评论到文件 comments_{video_id}.json")
                
                # 更新最终进度并标记完成
                self.progress.update_progress(video_id, current_title, init_count + comment_count, 0)
                self.progress.mark_completed(video_id)
                
                # 触发回调
                if self._progress_callback:
                    self._progress_callback(self.progress.get_status())
                    
            except Exception as e:
                import traceback
                print(f"爬取视频 {video_id} 失败: {e}")
                self.progress.mark_failed(video_id)
                if self._progress_callback:
                    self._progress_callback(self.progress.get_status())
            
            # 间隔一下，避免请求过快 (最后一条不等待)
            if i < len(remaining_ids) - 1:
                # 使用带有随机抖动的间隔
                actual_delay = _get_random_sleep(
                    config.CRAWLER_MIN_SLEEP_SEC,
                    config.CRAWLER_MAX_SLEEP_SEC,
                    config.CRAWLER_USE_JITTER,
                    config.CRAWLER_JITTER_RATIO
                )
                print(f"等待 {actual_delay:.2f} 秒后继续...")
                await asyncio.sleep(actual_delay)
        
        self.progress.finish()
        if self._progress_callback:
            self._progress_callback(self.progress.get_status())
        
        return {
            "videos": all_videos,
            "comments": all_comments,
            "total_comments": len(all_comments),
            "completed_count": len(remaining_ids),
        }
    
    async def close(self) -> None:
        """关闭爬虫"""
        try:
            if self.browser_context:
                await self.browser_context.close()
        except Exception:
            pass
        
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass
