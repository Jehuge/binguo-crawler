# -*- coding: utf-8 -*-
"""
抖音 API 客户端
"""
import asyncio
import copy
import json
import os
import random
import time
import urllib.parse
from typing import Any, Dict, List, Optional

import execjs
import httpx
from playwright.async_api import Page

import config
from utils import get_timestamp

# 加载抖音签名 JS
DOUYIN_JS_PATH = os.path.join(os.path.dirname(__file__), "libs", "douyin.js")
print(f"加载 douyin.js 从: {DOUYIN_JS_PATH}")
print(f"文件存在: {os.path.exists(DOUYIN_JS_PATH)}")
try:
    if os.path.exists(DOUYIN_JS_PATH):
        douyin_sign_obj = execjs.compile(open(DOUYIN_JS_PATH, encoding='utf-8-sig').read())
        print(f"douyin_sign_obj 加载成功: {douyin_sign_obj}")
    else:
        douyin_sign_obj = None
        print("douyin.js 文件不存在")
except Exception as e:
    douyin_sign_obj = None
    print(f"加载 douyin_sign_obj 失败: {e}")


class DouYinClient:
    """抖音 API 客户端"""

    # 类级别的风控状态追踪
    _risk_control_count = 0  # 连续风控次数
    _last_risk_time = 0  # 上次触发风控的时间
    _is_in_cooldown = False  # 是否在冷却期

    def __init__(
        self,
        timeout: int = 60,
        proxy: Optional[str] = None,
        headers: Optional[Dict] = None,
        playwright_page: Optional[Page] = None,
        browser_context = None,
    ):
        self.timeout = timeout
        self.proxy = proxy
        self.headers = headers or {}
        self._host = "https://www.douyin.com"
        self.playwright_page = playwright_page
        self.browser_context = browser_context  # 用于刷新 cookies

    def _get_jittered_sleep_time(self, base_time: float) -> float:
        """获取带有随机抖动的时间
        
        Args:
            base_time: 基础时间（秒）
            
        Returns:
            添加了随机抖动的时间
        """
        if not getattr(config, 'CRAWLER_USE_JITTER', True):
            return base_time
        
        jitter_ratio = getattr(config, 'CRAWLER_JITTER_RATIO', 0.3)
        # 在基础时间上增加 ±jitter_ratio 的随机波动
        jitter = base_time * jitter_ratio * (random.random() * 2 - 1)
        return max(0.5, base_time + jitter)  # 确保至少0.5秒
    
    async def _risk_control_sleep(self):
        """风控后的睡眠处理"""
        current_time = time.time()
        
        # 检查是否在冷却期
        cooldown = getattr(config, 'RISK_CONTROL_COOLDOWN', 300)
        if DouYinClient._is_in_cooldown:
            if current_time - DouYinClient._last_risk_time < cooldown:
                remaining = cooldown - (current_time - DouYinClient._last_risk_time)
                print(f"⚠️ 账号处于风控冷却期，等待 {remaining:.0f} 秒...")
                await asyncio.sleep(remaining)
                return
            else:
                # 冷却期结束，重置状态
                DouYinClient._is_in_cooldown = False
                DouYinClient._risk_control_count = 0
                print("✅ 风控冷却期结束，恢复爬取")
        
        # 正常请求间隔（带抖动）
        min_sleep = getattr(config, 'CRAWLER_MIN_SLEEP_SEC', 3)
        max_sleep = getattr(config, 'CRAWLER_MAX_SLEEP_SEC', 8)
        # 随机选择间隔时间
        sleep_time = random.uniform(min_sleep, max_sleep)
        sleep_time = self._get_jittered_sleep_time(sleep_time)
        await asyncio.sleep(sleep_time)

    async def _refresh_cookies(self):
        """刷新 cookies"""
        if self.browser_context:
            try:
                cookies = await self.browser_context.cookies()
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                self.headers["Cookie"] = cookie_str
                print(f"Cookies 已刷新: {cookie_str[:50]}...")
            except Exception as e:
                print(f"刷新 cookies 失败: {e}")

    async def _process_req_params(
        self,
        uri: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        request_method: str = "GET",
    ):
        """处理请求参数"""
        if not params:
            return
        headers = headers or self.headers
        
        # 检查 playwright_page 是否有效
        if self.playwright_page is None:
            raise Exception("playwright_page is None")
        
        try:
            local_storage: Dict = await self.playwright_page.evaluate("() => window.localStorage")
        except Exception as e:
            print(f"获取 localStorage 失败: {e}")
            local_storage = {}
        
        common_params = {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "version_code": "190600",
            "version_name": "19.6.0",
            "update_version_code": "170400",
            "pc_client_type": "1",
            "cookie_enabled": "true",
            "browser_language": "zh-CN",
            "browser_platform": "MacIntel",
            "browser_name": "Chrome",
            "browser_version": "125.0.0.0",
            "browser_online": "true",
            "engine_name": "Blink",
            "os_name": "Mac OS",
            "os_version": "10.15.7",
            "cpu_core_num": "8",
            "device_memory": "8",
            "engine_version": "109.0",
            "platform": "PC",
            "screen_width": "2560",
            "screen_height": "1440",
            "effective_type": "4g",
            "round_trip_time": "50",
            "webid": self._get_web_id(),
            "msToken": local_storage.get("xmst", ""),
        }
        params.update(common_params)
        query_string = urllib.parse.urlencode(params)

        # 获取 a_bogus 签名
        a_bogus = ""
        try:
            # 20240927 a-bogus update (JS version)
            post_data = {}
            if request_method == "POST":
                post_data = params
            
            if "/v1/web/general/search" not in uri:
                a_bogus = await self.get_a_bogus(uri, query_string, post_data, headers.get("User-Agent", ""))
                if a_bogus:
                    params["a_bogus"] = a_bogus
        except Exception as e:
            print(f"生成 a_bogus 失败: {e}")

    def _get_web_id(self) -> str:
        """生成 web_id"""
        import random
        import time
        return str(int(time.time() * 1000)) + str(random.randint(100000, 999999))

    async def request(self, method: str, url: str, **kwargs):
        """发送请求"""
        # 打印调试信息
        print(f"请求: {method} {url}")
        if 'params' in kwargs:
            params_str = str(kwargs['params'])
            # 检查是否有 a_bogus
            has_a_bogus = 'a_bogus' in kwargs['params'] if kwargs['params'] else False
            print(f"参数: {params_str[:200]}... a_bogus={'有' if has_a_bogus else '无'}")
        if 'headers' in kwargs:
            print(f"Headers Cookie: {kwargs['headers'].get('Cookie', '')[:50]}...")
        
        async with httpx.AsyncClient(proxy=self.proxy) as client:
            response = await client.request(method, url, timeout=self.timeout, **kwargs)
        
        print(f"响应状态: {response.status_code}")
        print(f"响应内容: {response.text[:500] if response.text else 'empty'}")
        
        # 检测响应类型
        content_type = response.headers.get("content-type", "")
        print(f"Content-Type: {content_type}")
        
        # 检测风控验证码标志
        bd_ticket_guard = response.headers.get("bd-ticket-guard-result", "")
        is_risk_triggered = False
        
        if bd_ticket_guard and bd_ticket_guard != "0":
            # 1101 表示有风控标记但未阻断，1100 表示正常
            if bd_ticket_guard == "1101":
                print(f"ℹ️ 风控标记 (code: {bd_ticket_guard}, 未阻断)")
                is_risk_triggered = True
            else:
                print(f"⚠️ 警告: 抖音验证码/风控触发 (code: {bd_ticket_guard})")
                is_risk_triggered = True
        
        # 检查是否返回了 HTML（可能是登录页面或验证码页面）
        if response.text.strip().startswith("<") or "html" in content_type.lower():
            print(f"⚠️ 警告: 收到HTML响应，可能是登录状态失效或需要验证码")
            is_risk_triggered = True
        
        # 风控处理
        if is_risk_triggered and getattr(config, 'ENABLE_RISK_CONTROL_DETECTION', True):
            DouYinClient._risk_control_count += 1
            DouYinClient._last_risk_time = time.time()
            
            print(f"⚠️ 检测到风控触发，连续风控次数: {DouYinClient._risk_control_count}")
            
            # 如果连续多次触发风控，进入冷却期
            max_retries = getattr(config, 'RISK_CONTROL_MAX_RETRIES', 3)
            if DouYinClient._risk_control_count >= max_retries:
                DouYinClient._is_in_cooldown = True
                cooldown = getattr(config, 'RISK_CONTROL_COOLDOWN', 300)
                print(f"⚠️ 连续 {DouYinClient._risk_control_count} 次触发风控，进入冷却期 {cooldown} 秒...")
                await asyncio.sleep(cooldown)
                # 冷却后重置计数
                DouYinClient._risk_control_count = 0
                DouYinClient._is_in_cooldown = False
            else:
                # 触发退避等待
                backoff_time = DouYinClient._risk_control_count * 5  # 递增等待
                print(f"⚠️ 触发退避，等待 {backoff_time} 秒后重试...")
                await asyncio.sleep(backoff_time)
        
        try:
            if response.text == "" or response.text == "blocked":
                raise Exception("账号可能被风控")
            return response.json()
        except Exception as e:
            text_preview = response.text[:200] if hasattr(response, "text") else "no text"
            # 详细打印异常信息帮助排查
            print(f"API请求解析失败详情: status={response.status_code}, text='{text_preview}', headers={dict(response.headers)}")
            raise Exception(f"API请求失败: {e}, status: {response.status_code}, body: {text_preview}")

    async def get(self, uri: str, params: Optional[Dict] = None, headers: Optional[Dict] = None):
        """GET 请求"""
        await self._refresh_cookies()
        await self._process_req_params(uri, params, headers)
        headers = headers or self.headers
        return await self.request(method="GET", url=f"{self._host}{uri}", params=params, headers=headers)

    async def post(self, uri: str, data: dict, headers: Optional[Dict] = None):
        """POST 请求"""
        await self._refresh_cookies()
        await self._process_req_params(uri, data, headers, "POST")
        headers = headers or self.headers
        return await self.request(method="POST", url=f"{self._host}{uri}", data=data, headers=headers)

    async def get_a_bogus(self, uri: str, query_string: str, post_data: Dict, user_agent: str) -> str:
        """获取 a_bogus 签名"""
        # 首先尝试使用 execjs
        if douyin_sign_obj:
            try:
                # 判断是详情接口还是回复接口
                sign_js_name = "sign_datail"
                if "/reply" in uri:
                    sign_js_name = "sign_reply"
                
                print(f"调用JS签名函数: {sign_js_name}, uri: {uri}")
                
                # 将 post_data 转换为字符串
                post_data_str = json.dumps(post_data) if post_data else ""
                
                # 调用 JS 函数获取签名
                a_bogus = douyin_sign_obj.call(sign_js_name, query_string, user_agent)
                print(f"JS签名生成结果: {a_bogus[:50] if a_bogus else 'empty'}...")
                if a_bogus:
                    return a_bogus
            except Exception as e:
                print(f"使用 execjs 获取 a_bogus 失败: {e}")
        
        # 如果 execjs 失败，尝试使用 playwright
        if self.playwright_page:
            try:
                a_bogus = await self.playwright_page.evaluate(
                    f"""
                    async () => {{
                        const a_bogus = await window._webid?.('{uri}', '{query_string}', '{post_data}', '{user_agent}');
                        return a_bogus;
                    }}
                    """
                )
                return a_bogus or ""
            except:
                pass
        
        return ""

    async def search_videos(
        self,
        keyword: str,
        offset: int = 0,
        sort_type: int = 0,  # 0: 综合, 1: 点赞最多, 2: 最新
        publish_time: int = 0,  # 0: 不限, 1: 一天内, 7: 一周内, 180: 半年内
        search_id: str = "",
    ) -> Dict:
        """
        搜索视频
        
        Args:
            keyword: 搜索关键字
            offset: 偏移量
            sort_type: 排序类型 (0: 综合, 1: 点赞最多, 2: 最新)
            publish_time: 发布时间 (0: 不限, 1: 一天内, 7: 一周内, 180: 半年内)
            search_id: 搜索 ID
        
        Returns:
            搜索结果
        """
        query_params = {
            "search_channel": "aweme_general",
            "enable_history": "1",
            "keyword": keyword,
            "search_source": "tab_search",
            "query_correct_type": "1",
            "is_filter_search": "0",
            "from_group_id": str(get_timestamp()),
            "offset": offset,
            "count": "15",
            "need_filter_settings": "1",
            "list_type": "multi",
            "search_id": search_id,
        }
        
        # 如果设置了排序或发布时间过滤
        if sort_type != 0 or publish_time != 0:
            query_params["filter_selected"] = json.dumps({
                "sort_type": str(sort_type),
                "publish_time": str(publish_time)
            })
            query_params["is_filter_search"] = "1"
            query_params["search_source"] = "tab_search"
        
        referer_url = f"https://www.douyin.com/search/{keyword}?aid=f594bbd9-a0e2-4651-9319-ebe3cb6298c1&type=general"
        headers = copy.copy(self.headers)
        headers["Referer"] = urllib.parse.quote(referer_url, safe=":/")
        
        return await self.get("/aweme/v1/web/general/search/single/", query_params, headers=headers)

    async def get_video_detail(self, aweme_id: str) -> Dict:
        """
        获取视频详情
        
        Args:
            aweme_id: 视频 ID
        
        Returns:
            视频详情
        """
        params = {"aweme_id": aweme_id}
        headers = copy.copy(self.headers)
        if "Origin" in headers:
            del headers["Origin"]
        res = await self.get("/aweme/v1/web/aweme/detail/", params, headers)
        return res.get("aweme_detail", {})

    async def get_comments(
        self,
        aweme_id: str,
        cursor: int = 0,
        count: int = 20,
    ) -> Dict:
        """
        获取视频评论
        
        Args:
            aweme_id: 视频 ID
            cursor: 游标
            count: 每页数量
        
        Returns:
            评论列表
        """
        uri = "/aweme/v1/web/comment/list/"
        params = {
            "aweme_id": aweme_id,
            "cursor": cursor,
            "count": count,
            "item_type": 0,
        }
        headers = copy.copy(self.headers)
        referer_url = f"https://www.douyin.com/video/{aweme_id}"
        headers["Referer"] = urllib.parse.quote(referer_url, safe=":/")
        return await self.get(uri, params, headers=headers)

    async def get_all_comments(
        self,
        aweme_id: str,
        crawl_interval: float = 1.0,
        max_count: int = 100,
        progress_callback = None,
        start_cursor: int = 0,
        fetch_sub_comments: bool = None,  # 是否获取子评论，默认读取配置
    ) -> List[Dict]:
        """
        获取视频所有评论 (包含子评论)
        
        Args:
            aweme_id: 视频 ID
            crawl_interval: 爬取间隔（秒）
            max_count: 最大评论数
            progress_callback: 进度回调函数
            start_cursor: 起始游标，用于断点续传
            fetch_sub_comments: 是否获取子评论，None 时读取配置文件
        
        Returns:
            评论列表
        """
        # 如果未指定，使用配置文件中的设置
        if fetch_sub_comments is None:
            try:
                from config import FETCH_SUB_COMMENTS
                fetch_sub_comments = FETCH_SUB_COMMENTS
            except ImportError:
                fetch_sub_comments = False
        
        print(f"获取评论配置: fetch_sub_comments={fetch_sub_comments}")
        
        result = []
        comments_has_more = 1
        comments_cursor = start_cursor
        
        while comments_has_more and len(result) < max_count:
            try:
                comments_res = await self.get_comments(aweme_id, comments_cursor)
                comments_has_more = comments_res.get("has_more", 0)
                comments_cursor = comments_res.get("cursor", 0)
                comments = comments_res.get("comments", [])
            except Exception as e:
                print(f"获取主评论异常 (aweme_id: {aweme_id}, cursor: {comments_cursor}): {e}")
                break
            
            if not comments:
                break
            
            if len(result) + len(comments) > max_count:
                comments = comments[:max_count - len(result)]
            
            result.extend(comments)
            
            if progress_callback:
                progress_callback(len(result), comments_cursor)
            
            # 使用带抖动的间隔，而不是固定的 crawl_interval
            min_sleep = getattr(config, 'CRAWLER_MIN_SLEEP_SEC', 3)
            max_sleep = getattr(config, 'CRAWLER_MAX_SLEEP_SEC', 8)
            sleep_time = random.uniform(min_sleep, max_sleep)
            if getattr(config, 'CRAWLER_USE_JITTER', True):
                jitter = sleep_time * getattr(config, 'CRAWLER_JITTER_RATIO', 0.3) * (random.random() * 2 - 1)
                sleep_time = max(0.5, sleep_time + jitter)
            await asyncio.sleep(sleep_time)
            
            # 抓取子评论（如果开启）
            if fetch_sub_comments:
                for comment in comments:
                    if len(result) >= max_count:
                        break
                        
                    reply_comment_total = comment.get("reply_comment_total", 0)
                    if reply_comment_total > 0:
                        comment_id = comment.get("cid")
                        sub_comments_has_more = 1
                        sub_comments_cursor = 0
                        
                        # 重置子评论重试计数
                        setattr(self, '_sub_comment_retry_count', 0)
                        
                        while sub_comments_has_more and len(result) < max_count:
                            try:
                                # 子评论请求间隔（降低延迟提高效率）
                                import random
                                await asyncio.sleep(random.uniform(0.3, 0.8))

                                sub_comments_res = await self.get_sub_comments(aweme_id, comment_id, sub_comments_cursor)
                                sub_comments_has_more = sub_comments_res.get("has_more", 0)
                                sub_comments_cursor = sub_comments_res.get("cursor", 0)
                                sub_comments = sub_comments_res.get("comments", [])
                                
                                # 成功获取数据后重置重试计数
                                setattr(self, '_sub_comment_retry_count', 0)
                            except Exception as e:
                                error_msg = str(e)
                                # 检查是否是风控导致的空响应
                                if "账号可能被风控" in error_msg or "empty" in error_msg.lower():
                                    # 遇到风控时，尝试重试（缩短等待时间）
                                    import random
                                    retry_count = getattr(self, '_sub_comment_retry_count', 0)
                                    if retry_count < 3:
                                        wait_time = 1.5 * (retry_count + 1) + random.uniform(0, 0.5)  # 线性退避
                                        print(f"检测到风控，{wait_time:.1f}秒后重试 (尝试 {retry_count + 1}/3)")
                                        await asyncio.sleep(wait_time)
                                        setattr(self, '_sub_comment_retry_count', retry_count + 1)
                                        continue  # 重试当前子评论
                                    else:
                                        # 重试次数用尽，记录并跳过
                                        print(f"子评论获取重试次数用尽 (comment_id: {comment_id}), 跳过该评论")
                                        setattr(self, '_sub_comment_retry_count', 0)
                                else:
                                    print(f"获取子评论异常 (comment_id: {comment_id}, cursor: {sub_comments_cursor}): {e}")
                                
                                # 遇到异常时退出当前子评论的获取，但保留主评论获取能力
                                sub_comments_has_more = 0
                                break
                            
                            if not sub_comments:
                                break
                                
                            if len(result) + len(sub_comments) > max_count:
                                sub_comments = sub_comments[:max_count - len(result)]
                                
                            result.extend(sub_comments)
                            
                            if progress_callback:
                                # 子评论获取后不影响主评论的 cursor，直接传回当前的主评论 cursor
                                progress_callback(len(result), comments_cursor)
                            
            if len(result) >= max_count:
                break
            
            # 如果遇到连续的异常风控，导致无法获取新数据，可能需要跳出防止死循环或被封禁
            if not comments:
                break
                
        # 兜底：如果有些原因没有返回列表
        return result if result is not None else []

    async def get_sub_comments(
        self,
        aweme_id: str,
        comment_id: str,
        cursor: int = 0,
        count: int = 20,
    ) -> Dict:
        """
        获取子评论
        
        Args:
            aweme_id: 视频 ID
            comment_id: 评论 ID
            cursor: 游标
            count: 每页数量
        
        Returns:
            子评论列表
        """
        print(f">>> 开始获取子评论: aweme_id={aweme_id}, comment_id={comment_id}, cursor={cursor}")
        
        uri = "/aweme/v1/web/comment/list/reply/"
        params = {
            "comment_id": comment_id,
            "cursor": cursor,
            "count": count,
            "item_type": 0,
            "item_id": aweme_id,
            # 添加 verifyFp 参数（可能有助于绕过风控）
            "verifyFp": "verify_ma3hrt8n_q2q2HyYA_uLyO_4N6D_BLvX_E2LgoGmkA1BU",
            "fp": "verify_ma3hrt8n_q2q2HyYA_uLyO_4N6D_BLvX_E2LgoGmkA1BU",
        }
        headers = copy.copy(self.headers)
        # 使用与主评论相同的 Referer 格式（搜索页面），避免被识别为爬虫
        referer_url = f"https://www.douyin.com/search/video?aid=3a3cec5a-9e27-4040-b6aa-ef548c2c1138&publish_time=0&sort_type=0&source=search_history&type=general"
        headers["Referer"] = urllib.parse.quote(referer_url, safe=":/")
        
        print(f">>> 子评论请求参数: {params}")
        
        result = await self.get(uri, params, headers=headers)
        
        print(f">>> 子评论响应: has_more={result.get('has_more')}, cursor={result.get('cursor')}, comments_count={len(result.get('comments', []))}")
        
        return result
