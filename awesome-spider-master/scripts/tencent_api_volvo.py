from __future__ import annotations

from scripts.common import build_parser, finalize_results
from spiders.tencent_spider import TencentSpider


def main() -> None:
    parser = build_parser("腾讯新闻 API 模式快速调试脚本", default_pages=3)
    parser.add_argument(
        "--time-slices",
        default="",
        help="自定义时间切片，使用逗号分隔，例如：9月,8月",
    )
    args = parser.parse_args()

    time_slices = [s.strip() for s in args.time_slices.split(",") if s.strip()] or None

    spider = TencentSpider()
    results = spider.crawl(
        args.keyword,
        time_slices=time_slices,
        max_pages=args.max_pages,
    )
    csv_time_range = args.time_range or args.time_slices

    finalize_results(
        results,
        keyword=args.keyword,
        time_range=csv_time_range,
        output_dir=args.output_dir,
        preview=args.preview,
        json_path=args.json,
    )


if __name__ == "__main__":
    main()
