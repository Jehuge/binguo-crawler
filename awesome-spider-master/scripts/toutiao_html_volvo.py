from __future__ import annotations

from scripts.common import build_parser, finalize_results
from spiders.toutiao_spider import ToutiaoSpider


def main() -> None:
    parser = build_parser("今日头条 HTML 模式快速调试脚本", default_pages=1)
    args = parser.parse_args()

    spider = ToutiaoSpider()
    results = spider.crawl(args.keyword, max_pages=args.max_pages)
    finalize_results(
        results,
        keyword=args.keyword,
        time_range=args.time_range,
        output_dir=args.output_dir,
        preview=args.preview,
        json_path=args.json,
    )


if __name__ == "__main__":
    main()
