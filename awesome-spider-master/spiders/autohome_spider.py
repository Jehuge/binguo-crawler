import json
import time
from typing import Any
from urllib.parse import quote

import requests
from requests.exceptions import RequestException


class AutohomeSpider:
    def __init__(self, advertiser: str = "未知广告主", debug: bool = True):
        self.advertiser = advertiser
        self.debug = debug
        self.base_url = "https://sou.api.autohome.com.cn/v1/search"

    def _fetch_page(self, keyword: str, page: int, page_size: int = 10) -> dict[str, Any]:
        offset = (page - 1) * page_size
        params = {
            "uuid": "16ade5b1-5954-4fe7-aa00-bf510aed3647",
            "source": "pc",
            "is_base_exp": 0,
            "modify": 0,
            "q": keyword,
            "entry": 42,
            "error": 0,
            "pvareaid": 6861421,
            "mq": "",
            "charset": "utf8",
            "pid": 90300023,
            "offset": offset,
            "size": page_size,
            "page": page,
            "ext": json.dumps(
                {
                    "chl": "",
                    "plat": "pc",
                    "pf": "h5",
                    "bbsId": "",
                    "q": keyword,
                    "offset": offset,
                    "size": page_size,
                    "modify": "0",
                    "cityid": 110100,
                    "perscont": "1",
                    "version": "1.0.3",
                    "box_count": 0,
                },
                ensure_ascii=False,
            ),
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/118.0 Safari/537.36"
            ),
            "Referer": f"https://sou.autohome.com.cn/zonghe?q={quote(keyword)}",
            "Origin": "https://sou.autohome.com.cn",
            "Accept": "application/json, text/plain, */*",
        }

        if self.debug:
            print(f"🔗 请求 API: {self.base_url}")
            print(f"📌 参数: {json.dumps(params, ensure_ascii=False)}")

        response = requests.get(self.base_url, params=params, headers=headers, timeout=30)

        if self.debug:
            print(f"📡 状态码: {response.status_code}")

        response.raise_for_status()
        data = response.json()

        if self.debug:
            print(f"📊 返回字段: {list(data.keys())}")
            result = data.get("result", {})
            print(
                f"📊 result keys: {list(result.keys()) if isinstance(result, dict) else 'None'}"
            )
            if "itemlist" in result:
                print(f"📊 itemlist 数量: {len(result.get('itemlist', []))}")

        return data

    def _crawl_api(self, keyword: str, max_pages: int = 10) -> list[dict[str, Any]]:
        all_results: list[dict[str, Any]] = []

        for page in range(1, max_pages + 1):
            print(f"\n🚀 抓取汽车之家第 {page} 页: {keyword}")
            try:
                data = self._fetch_page(keyword, page)
            except RequestException as exc:
                print(f"❌ 请求失败: {exc}")
                break

            result = data.get("result", {})
            itemlist = result.get("itemlist", [])
            if not itemlist:
                print("⚠️ 没有更多数据，提前结束")
                break

            for idx, block in enumerate(itemlist, start=1):
                iteminfo = block.get("iteminfo", {})
                box_type = iteminfo.get("type")
                if box_type not in ("news_3gc", "video_3gc"):
                    if self.debug:
                        print(f"ℹ️ [page {page}-{idx}] 跳过 {box_type}")
                    continue

                for subitem in iteminfo.get("data", {}).get("itemlist", []):
                    show = subitem.get("iteminfo", {}).get("show", {})
                    title = show.get("title") or ""
                    url = show.get("jump_url2") or show.get("m_jump") or ""
                    publish_date = show.get("publish_time", "")

                    if title and url:
                        all_results.append(
                            {
                                "site_name": "汽车之家",
                                "advertiser": keyword,
                                "title": title,
                                "url": url,
                                "date": publish_date[:10],
                            }
                        )

                        if self.debug:
                            print(f"📌 {title} | {url} | 日期: {publish_date[:10]}")

            time.sleep(1.5)

        print(f"\n✅ API 模式完成，共抓取 {len(all_results)} 条记录")
        return all_results

    def crawl(self, keyword: str, max_pages: int = 5) -> list[dict[str, Any]]:
        """执行推荐的 JSON API 采集模式。"""
        self.advertiser = keyword
        return self._crawl_api(keyword, max_pages=max_pages)
