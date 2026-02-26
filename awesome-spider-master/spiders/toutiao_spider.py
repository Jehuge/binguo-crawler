import json
import os
import time
from typing import Any

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ------------------- 环境变量 -------------------
load_dotenv()
CHROME_BINARY_PATH = os.getenv("CHROME_BINARY_PATH")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH")
SEARCH_URL = os.getenv("TOUTIAO_SEARCH_URL")  # 必须在 .env 中设置
PAGE_SLEEP_TIME = int(os.getenv("PAGE_SLEEP_TIME", "3"))


class ToutiaoSpider:
    def __init__(self, advertiser: str = "未知广告主", debug: bool = True) -> None:
        self.advertiser = advertiser
        self.debug = debug
        self.chrome_path = CHROME_BINARY_PATH
        self.driver_path = CHROMEDRIVER_PATH

    # ------------------- HTML 模式 -------------------
    def _ensure_browser_paths(self) -> None:
        if not self.chrome_path or not self.driver_path:
            raise ValueError("❌ 请在 .env 中配置 CHROME_BINARY_PATH 和 CHROMEDRIVER_PATH")

    def _init_driver(self) -> uc.Chrome:
        """初始化 ChromeDriver"""
        self._ensure_browser_paths()
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/118.0.5993.90 Safari/537.36"
        )
        driver = uc.Chrome(
            options=options,
            browser_executable_path=self.chrome_path,
            driver_executable_path=self.driver_path,
        )
        return driver

    def _build_search_url(self, keyword: str, page: int) -> str:
        if not SEARCH_URL:
            raise ValueError("❌ 请在 .env 中设置 TOUTIAO_SEARCH_URL，且包含 KEYWORD 占位符")
        base = SEARCH_URL.replace("KEYWORD", keyword)
        if page == 1:
            return base
        return (
            base.replace("source=input", "source=pagination")
            + f"&pd=synthesis&action_type=pagination&page_num={page}"
        )

    def _extract_articles(self, html: str) -> list[dict[str, Any]]:
        """从今日头条搜索结果页提取文章信息"""
        soup = BeautifulSoup(html, "html.parser")
        articles: list[dict[str, Any]] = []

        scripts = soup.find_all("script", {"type": "application/json", "id": True})
        scripts = [s for s in scripts if s["id"].startswith("s-data-")]

        if self.debug:
            print(f"🔎 找到 {len(scripts)} 个 <script id='s-data-...'> 节点")

        for script in scripts:
            try:
                raw_text = script.text.strip()
                data = json.loads(raw_text)
                d = data.get("data", {})

                title = d.get("title")
                item_id = d.get("id") or d.get("item_id")
                behot_time = d.get("behot_time")

                if not title or not item_id:
                    continue

                url = f"http://m.toutiao.com/group/{item_id}/"
                publish_date = (
                    time.strftime("%Y-%m-%d", time.localtime(int(behot_time)))
                    if behot_time
                    else ""
                )

                articles.append(
                    {
                        "site_name": "今日头条",
                        "advertiser": self.advertiser,
                        "title": title,
                        "url": url,
                        "date": publish_date,
                    }
                )

            except Exception as e:  # noqa: BLE001 - 调试日志即可
                if self.debug:
                    print(f"❌ JSON 解析失败: {e}")

        return articles

    def _crawl_html(self, keyword: str, max_pages: int) -> list[dict[str, Any]]:
        """使用浏览器渲染页面并解析 HTML"""
        self.advertiser = keyword
        driver = self._init_driver()
        all_articles: list[dict[str, Any]] = []

        try:
            for page in range(1, max_pages + 1):
                url = self._build_search_url(keyword, page)
                print(f"🌍 正在抓取第 {page} 页: {url}")
                driver.get(url)
                time.sleep(PAGE_SLEEP_TIME + 2)

                page_articles = self._extract_articles(driver.page_source)
                if not page_articles:
                    print("⚠️ 本页没有抓到文章，可能已经到底。")
                    break

                all_articles.extend(page_articles)
        finally:
            driver.quit()

        print(f"🎉 HTML 模式完成，共 {len(all_articles)} 条")
        return all_articles

    # ------------------- 公共接口 -------------------
    def crawl(self, keyword: str, max_pages: int = 10) -> list[dict[str, Any]]:
        """执行推荐的 HTML 解析流程。"""
        return self._crawl_html(keyword, max_pages=max_pages)
