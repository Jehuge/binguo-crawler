import random
import time
from typing import Any
from urllib.parse import quote

import requests
from requests.exceptions import ReadTimeout, RequestException, SSLError


class TencentSpider:
    def __init__(
        self,
        advertiser: str = "未知广告主",
        debug: bool = True,
        time_slices: list[str] | None = None,
    ) -> None:
        if time_slices is None:
            time_slices = ["9月", "8月", "7月"]
        self.advertiser = advertiser
        self.debug = debug
        self.time_slices = time_slices

    def _fetch_page(self, keyword: str, page: int, page_size: int = 10) -> dict[str, Any]:
        """请求腾讯新闻搜索接口的一页数据。"""
        url = "https://i.news.qq.com/gw/pc_search/result"
        params = {
            "query": keyword,
            "page": page,
            "is_pc": 1,
            "hippy_custom_version": 25,
            "search_type": "all",
            "search_count_limit": page_size,
            "appver": "15.5_qqnews_7.1.80",
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/118.0.5993.90 Safari/537.36"
            ),
            "Referer": f"https://news.qq.com/search?query={quote(keyword)}",
            "Origin": "https://news.qq.com",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        for attempt in range(3):
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
                return resp.json()
            except (SSLError, ReadTimeout, RequestException) as exc:
                wait_time = 2 + attempt * 3
                print(f"⚠️ 请求失败（第 {attempt + 1} 次）: {exc} → {wait_time}s 后重试")
                time.sleep(wait_time)
        return {}

    def _crawl_api(
        self,
        keyword: str,
        time_slices: list[str] | None,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        """循环时间切片并抓取 API 结果。"""
        self.advertiser = keyword
        all_articles: list[dict[str, Any]] = []

        if not time_slices:
            time_slices = self.time_slices

        for idx, slice_kw in enumerate(time_slices):
            full_kw = f"{keyword} {slice_kw}".strip()
            print(f"\n🚀 开始爬取: {full_kw}")

            for page in range(max_pages):
                print(f"🌍 抓取 {full_kw} - 第 {page + 1} 页")
                data = self._fetch_page(full_kw, page)
                if not data:
                    print("⚠️ 请求失败或无数据，跳过")
                    break

                sec_list = data.get("secList", [])
                if not sec_list:
                    print("⚠️ 没有更多数据，停止")
                    break

                for sec in sec_list:
                    for item in sec.get("newsList", []):
                        title = item.get("title")
                        url = item.get("url")
                        publish_time = item.get("time")
                        ts = item.get("timestamp")

                        publish_date = publish_time or (
                            time.strftime("%Y-%m-%d") if ts else ""
                        )

                        if title and url:
                            all_articles.append(
                                {
                                    "site_name": "腾讯新闻",
                                    "advertiser": self.advertiser,
                                    "title": title,
                                    "url": url,
                                    "date": publish_date,
                                }
                            )

                time.sleep(random.uniform(2, 5))

            if idx < len(time_slices) - 1:
                print("⏳ 切换时间片，休眠 10 秒防风控")
                time.sleep(10)

        print(f"\n✅ API 爬虫完成，共抓取 {len(all_articles)} 条文章")
        return all_articles

    def crawl(
        self,
        keyword: str,
        time_slices: list[str] | None = None,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """执行推荐的 JSON API 采集模式。"""
        return self._crawl_api(keyword, time_slices=time_slices, max_pages=max_pages)
