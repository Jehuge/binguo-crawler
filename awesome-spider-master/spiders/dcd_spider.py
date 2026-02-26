import os
import re
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from selenium import webdriver

from spiders.base_spider import BaseSpider
from util.dcd_browser import load_driver_with_cookies

# 加载环境变量
load_dotenv()


def _smart_scroll(driver, steps: int = 20, pause: int = 2) -> None:
    """模拟滚动加载更多内容"""
    for _ in range(steps):
        driver.execute_script("window.scrollBy(0, document.body.scrollHeight/2);")
        time.sleep(pause)


def _extract_news_time(news_time: str, current_date: datetime, three_months_ago: datetime) -> str | None:
    """解析新闻时间字段，兼容多种格式"""
    if not news_time or news_time == "未知":
        return None

    try:
        if "分钟" in news_time or "小时" in news_time or "刚刚" in news_time:
            return current_date.strftime("%Y-%m-%d")
        elif "昨天" in news_time:
            return (current_date - timedelta(days=1)).strftime("%Y-%m-%d")
        elif "前天" in news_time:
            return (current_date - timedelta(days=2)).strftime("%Y-%m-%d")
        elif "天前" in news_time:
            m = re.search(r"(\d+)天前", news_time)
            if m:
                return (current_date - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")

        # 处理 09-10 或 2025-09-10 或 09-10 10:30
        if "-" in news_time:
            parts = news_time.split(" ")[0]  # 取日期部分
            if len(parts) == 5:  # 09-10
                news_date_str = f"{current_date.year}-{parts}"
                news_date = datetime.strptime(news_date_str, "%Y-%m-%d")
            elif len(parts) == 10:  # 2025-09-10
                news_date = datetime.strptime(parts, "%Y-%m-%d")
            else:
                return None

            if news_date.month > current_date.month:  # 跨年修正
                news_date = news_date.replace(year=current_date.year - 1)
            if news_date >= three_months_ago:
                return news_date.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"⚠️ 时间解析失败: {news_time}, 错误: {e}")
    return None


class DcdSpider(BaseSpider):
    """懂车帝爬虫，仅保留浏览器渲染模式。"""

    def __init__(self) -> None:
        self.chrome_path = os.getenv("CHROME_BINARY_PATH")
        self.driver_path = os.getenv("CHROMEDRIVER_PATH")
        self.advertiser = "未知广告主"

    # ---------------------------- HTML 模式 ----------------------------
    def _ensure_browser_paths(self) -> None:
        if not self.chrome_path or not self.driver_path:
            raise ValueError("❌ 请在 .env 中配置 CHROME_BINARY_PATH 和 CHROMEDRIVER_PATH")

    def _parse_page(
        self, driver: webdriver.Chrome, keyword: str, current_date: datetime, three_months_ago: datetime
    ) -> list[dict[str, Any]]:
        """解析页面文章/视频"""
        soup = BeautifulSoup(driver.page_source, "html.parser")
        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        cards = soup.select("div.common-card_wrapper__Inr_n")
        print(f"👉 找到 {len(cards)} 条内容")

        for card in cards:
            a = card.select_one("h3 a[href]")
            if not a:
                continue
            title = a.get_text(strip=True)
            url = a["href"]
            if not url.startswith("http"):
                url = "https://www.dongchedi.com" + url

            if url in seen_urls:
                continue
            seen_urls.add(url)

            # 修正时间获取逻辑
            spans = card.select("p span")
            time_tag = spans[-1] if spans else None
            raw_time = time_tag.get_text(strip=True) if time_tag else "未知"

            parsed_time = _extract_news_time(raw_time, current_date, three_months_ago)
            if not parsed_time:
                continue

            results.append(
                {
                    "site_name": "懂车帝",
                    "advertiser": keyword,
                    "date": parsed_time,
                    "title": title,
                    "url": url,
                }
            )
        return results

    def _crawl_html(self, keyword: str, max_pages: int) -> list[dict[str, Any]] | None:
        """通过浏览器解析页面"""
        self._ensure_browser_paths()
        driver = load_driver_with_cookies(start_url="https://www.dongchedi.com")
        results: list[dict[str, Any]] = []

        try:
            encoded_kw = urllib.parse.quote(keyword)
            search_url = f"https://www.dongchedi.com/search?keyword={encoded_kw}&currTab=1&search_mode=history"
            print(f"🔎 打开懂车帝搜索: {search_url}")
            driver.get(search_url)
            time.sleep(3)

            current_date = datetime.now()
            three_months_ago = current_date - timedelta(days=90)

            # 根据 max_pages 动态滚动
            _smart_scroll(driver, steps=max_pages * 10, pause=2)

            page_results = self._parse_page(driver, keyword, current_date, three_months_ago)
            results.extend(page_results)
        except Exception as e:
            print(f"❌ 爬取出错: {e}")
        finally:
            try:
                driver.quit()
            except Exception:
                pass

        print(f"🎉 HTML 模式完成，共 {len(results)} 条")
        return results

    # ---------------------------- 公共接口 ----------------------------
    def crawl(self, keyword: str, max_pages: int = 1) -> list[dict[str, Any]]:
        """执行爬取（仅 HTML 模式）。"""
        self.advertiser = keyword
        return self._crawl_html(keyword, max_pages=max_pages)
