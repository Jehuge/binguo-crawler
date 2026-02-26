import requests
from bs4 import BeautifulSoup


class YiCheSpider:
    def __init__(self, keyword="沃尔沃", max_pages=3):
        self.keyword = keyword
        self.max_pages = max_pages
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/118.0.5993.90 Safari/537.36"
        }

    def _fetch_page(self, url):
        """请求网页并返回 soup"""
        resp = requests.get(url, headers=self.headers, timeout=15)
        if resp.status_code != 200:
            print(f"❌ 请求失败 {resp.status_code}: {url}")
            return None
        return BeautifulSoup(resp.text, "lxml")

    def fetch_news(self):
        """爬取新闻文章"""
        results = []
        base_url = f"https://so.yiche.com/xinwen/{self.keyword}/"
        for page in range(1, self.max_pages + 1):
            url = base_url if page == 1 else f"{base_url}?page={page}"
            print(f"📰 抓取新闻: {url}")
            soup = self._fetch_page(url)
            if not soup:
                continue

            for item in soup.select(".search-result-item"):
                title_tag = item.select_one(".tit a")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                link = title_tag["href"]
                summary = item.select_one(".desc")
                date = item.select_one(".time")
                results.append({
                    "type": "新闻",
                    "title": title,
                    "url": link,
                    "summary": summary.get_text(strip=True) if summary else "",
                    "date": date.get_text(strip=True) if date else ""
                })
        return results


    def fetch_videos(self):
        """爬取视频"""
        results = []
        base_url = f"https://so.yiche.com/shipin/{self.keyword}/"
        for page in range(1, self.max_pages + 1):
            url = base_url if page == 1 else f"{base_url}?page={page}"
            print(f"🎬 抓取视频: {url}")
            soup = self._fetch_page(url)
            if not soup:
                continue

            for item in soup.select(".search-result-item"):
                title_tag = item.select_one(".tit a")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                link = title_tag["href"]
                duration = item.select_one(".time")
                results.append(
                    {
                        "type": "视频",
                        "title": title,
                        "url": link,
                        "duration": duration.get_text(strip=True) if duration else "",
                        "date": "",
                    }
                )
        return results
