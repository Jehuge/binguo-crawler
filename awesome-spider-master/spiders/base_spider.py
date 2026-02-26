class BaseSpider:
    def crawl(self, keyword: str, max_pages: int, mode: str = "html") -> list[dict]:
        raise NotImplementedError("必须实现 crawl 方法")
