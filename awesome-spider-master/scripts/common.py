from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence

from util.save_to_csv import save_to_csv

KEYWORD = "沃尔沃"
DEFAULT_TIME_RANGE = "全部时间"


def add_project_root() -> Path:
    """Ensure the project root is available on ``sys.path``."""
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    return project_root


PROJECT_ROOT = add_project_root()


def build_parser(description: str, default_pages: int = 1) -> argparse.ArgumentParser:
    """Create a shared CLI parser used by all quick-start scripts."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--keyword",
        default=KEYWORD,
        help="搜索关键词，默认为沃尔沃",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=default_pages,
        help="最大翻页/滚动次数，避免调试时抓取过多数据",
    )
    parser.add_argument(
        "--preview",
        type=int,
        default=5,
        help="打印前 N 条结果预览，设为 0 可关闭预览",
    )
    parser.add_argument(
        "--json",
        type=str,
        help="若提供路径，则将完整结果保存为 JSON 文件",
    )
    parser.add_argument(
        "--time-range",
        default=DEFAULT_TIME_RANGE,
        help="时间范围描述，将用于生成 CSV 文件名",
    )
    parser.add_argument(
        "--output-dir",
        default="output/csv",
        help="CSV 输出目录，默认为 output/csv",
    )
    return parser


def finalize_results(
    results: Sequence[dict[str, object]],
    *,
    keyword: str,
    time_range: str = DEFAULT_TIME_RANGE,
    output_dir: str = "output/csv",
    preview: int = 5,
    json_path: str | None = None,
) -> None:
    """Print a short summary and optionally save results to disk."""
    data = list(results)
    print(f"🎯 共抓取 {len(data)} 条记录")

    if preview:
        snippet = data[:preview]
        if snippet:
            print("👀 结果预览：")
            print(json.dumps(snippet, ensure_ascii=False, indent=2))
        else:
            print("⚠️ 暂无可展示的结果")

    if json_path:
        output_path = Path(json_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"💾 已保存 JSON 至 {output_path}")

    csv_records = _prepare_csv_records(data, keyword=keyword)
    if not csv_records:
        return

    filename = _build_csv_filename(csv_records[0]["site_name"], keyword, time_range)
    output_path = Path(output_dir) / filename
    save_to_csv(csv_records, filename=str(output_path))


def _prepare_csv_records(
    data: Sequence[dict[str, object]], *, keyword: str
) -> list[dict[str, str]]:
    """Normalize records so they match the CSV schema."""

    records: list[dict[str, str]] = []
    for item in data:
        site_name = str(item.get("site_name") or "未知网站")
        advertiser = str(item.get("advertiser") or keyword)
        title = str(item.get("title") or "")
        url = str(item.get("url") or "")
        date_value = _normalize_date(item.get("date"))

        records.append(
            {
                "site_name": site_name,
                "advertiser": advertiser,
                "date": date_value,
                "title": title,
                "url": url,
            }
        )

    return records


def _normalize_date(value: object) -> str:
    """Convert assorted date representations to yyyy-mm-dd."""

    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value).strftime("%Y-%m-%d")
        except (OSError, ValueError):
            return ""

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""

        today = datetime.today()

        if any(token in text for token in ["刚刚", "分钟", "小时", "今日", "今天"]):
            return today.strftime("%Y-%m-%d")
        if "昨天" in text:
            return (today - timedelta(days=1)).strftime("%Y-%m-%d")
        if "前天" in text:
            return (today - timedelta(days=2)).strftime("%Y-%m-%d")

        cleaned = (
            text.replace("年", "-")
            .replace("月", "-")
            .replace("日", "")
            .replace("/", "-")
            .replace(".", "-")
            .strip()
        )
        cleaned = re.split(r"[ T]", cleaned)[0]

        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        if re.fullmatch(r"\d{4}\d{2}\d{2}", cleaned):
            return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"

        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", cleaned):
            year, month, day = cleaned.split("-")
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

        if re.fullmatch(r"\d{1,2}-\d{1,2}", cleaned):
            month, day = cleaned.split("-")
            try:
                dt = datetime(today.year, int(month), int(day))
            except ValueError:
                return ""
            if dt > today:
                dt = dt.replace(year=today.year - 1)
            return dt.strftime("%Y-%m-%d")

    return ""


def _build_csv_filename(site_name: str, keyword: str, time_range: str) -> str:
    """Generate a descriptive CSV filename."""

    site_component = _sanitize_filename_component(site_name or "site")
    keyword_component = _sanitize_filename_component(keyword or KEYWORD)
    time_component = _sanitize_filename_component(time_range or DEFAULT_TIME_RANGE)
    return f"{site_component}_{keyword_component}_{time_component}.csv"


def _sanitize_filename_component(value: str) -> str:
    text = value.strip()
    if not text:
        return _sanitize_filename_component(DEFAULT_TIME_RANGE)

    text = re.sub(r"[\\s/\\\\]+", "_", text)
    text = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]", "", text)
    sanitized = text.strip("_-")
    return sanitized or "default"
