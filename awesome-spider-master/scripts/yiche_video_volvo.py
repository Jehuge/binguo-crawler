from __future__ import annotations

from scripts.common import build_parser, finalize_results
from spiders.yiche_spider import YiCheSpider


def main() -> None:
    parser = build_parser("易车网 视频模式快速调试脚本", default_pages=3)
    args = parser.parse_args()

    spider = YiCheSpider(keyword=args.keyword, max_pages=args.max_pages)
    raw_results = spider.fetch_videos()
    results = [
        {
            "site_name": "易车网",
            "advertiser": args.keyword,
            **item,
        }
        for item in raw_results
    ]
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
