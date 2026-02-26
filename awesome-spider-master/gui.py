import os
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk, messagebox

from spiders.autohome_spider import AutohomeSpider
from spiders.dcd_spider import DcdSpider
from spiders.tencent_spider import TencentSpider
from spiders.toutiao_spider import ToutiaoSpider
from spiders.yiche_spider import YiCheSpider
from util.save_to_csv import save_to_csv

Runner = Callable[[str], list[dict[str, object]]]


def _run_toutiao(keyword: str) -> list[dict[str, object]]:
    return ToutiaoSpider().crawl(keyword, max_pages=10)


def _run_dcd(keyword: str) -> list[dict[str, object]]:
    return DcdSpider().crawl(keyword, max_pages=5)


def _run_tencent(keyword: str) -> list[dict[str, object]]:
    return TencentSpider().crawl(keyword, max_pages=5)


def _run_autohome(keyword: str) -> list[dict[str, object]]:
    return AutohomeSpider().crawl(keyword, max_pages=5)


def _run_yiche(keyword: str) -> list[dict[str, object]]:
    spider = YiCheSpider(keyword=keyword, max_pages=3)
    news = [
        {"site_name": "易车网", "advertiser": keyword, **item}
        for item in spider.fetch_news()
    ]
    videos = [
        {"site_name": "易车网", "advertiser": keyword, **item}
        for item in spider.fetch_videos()
    ]
    return news + videos


SITE_RUNNERS: dict[str, tuple[str, Runner]] = {
    "今日头条": ("html", _run_toutiao),
    "懂车帝": ("html", _run_dcd),
    "腾讯新闻": ("api", _run_tencent),
    "汽车之家": ("api", _run_autohome),
    "易车网": ("api", _run_yiche),
}


# 从 .env 读取关键词
keywords = os.getenv("KEYWORDS", "")
keyword_list = [kw.strip() for kw in keywords.split(",") if kw.strip()]


def run_spider() -> None:
    selected_indices = keyword_listbox.curselection()
    if not selected_indices:
        messagebox.showwarning("警告", "请选择至少一个关键词")
        return

    site = site_var.get()
    config = SITE_RUNNERS.get(site)
    if not config:
        messagebox.showwarning("警告", f"不支持的网站: {site}")
        return

    mode, runner = config

    for idx in selected_indices:
        kw = keyword_list[idx]
        print(f"🚀 开始爬取 {site} - {kw} - 模式={mode}")

        results = runner(kw)

        if results:
            os.makedirs("output", exist_ok=True)
            out_file = f"output/{site}_{kw}_{mode}.csv"
            save_to_csv(results, filename=out_file)
            messagebox.showinfo(
                "完成",
                f"{site} - {kw} - {mode} 爬取完成，共 {len(results)} 条，已保存到 {out_file}",
            )
        else:
            messagebox.showinfo("提示", f"{site} - {kw} 没有抓到数据")


# ------------------- GUI 界面 -------------------
root = tk.Tk()
root.title("🚗 AwesomeSpider")
root.geometry("700x480")
root.configure(bg="#f5f7fa")

# ttk 样式美化
style = ttk.Style()
style.theme_use("clam")

style.configure("TLabel", font=("微软雅黑", 11), background="#f5f7fa")
style.configure("TButton", font=("微软雅黑", 11), padding=6)
style.configure("TCombobox", font=("微软雅黑", 11))
style.configure("TListbox", font=("微软雅黑", 11))

# 标题栏
title_label = tk.Label(
    root, text="便捷爬虫工具", font=("微软雅黑", 18, "bold"), bg="#3f72af", fg="white", pady=12
)
title_label.pack(fill="x")

# 主容器（卡片风格）
main_frame = tk.Frame(root, bg="white", bd=2, relief="groove")
main_frame.pack(padx=20, pady=20, fill="both", expand=True)

# 网站选择
tk.Label(main_frame, text="网站:", font=("微软雅黑", 11), bg="white").grid(row=0, column=0, padx=10, pady=10, sticky="e")
site_var = tk.StringVar(value="今日头条")
site_combo = ttk.Combobox(
    main_frame,
    textvariable=site_var,
    values=["今日头条", "懂车帝", "腾讯新闻", "汽车之家", "易车网"],
    state="readonly",
    width=20
)
site_combo.grid(row=0, column=1, padx=10, pady=10, sticky="w")

# 关键词选择
tk.Label(main_frame, text="关键词:", font=("微软雅黑", 11), bg="white").grid(row=1, column=0, padx=10, pady=10, sticky="ne")
keyword_listbox = tk.Listbox(main_frame, selectmode=tk.MULTIPLE, height=8, width=28, font=("微软雅黑", 11))
for kw in keyword_list:
    keyword_listbox.insert(tk.END, kw)
keyword_listbox.grid(row=1, column=1, padx=10, pady=10, sticky="w")

# 开始按钮
start_btn = ttk.Button(main_frame, text="🚀 开始爬取", command=run_spider)
start_btn.grid(row=2, column=0, columnspan=2, pady=20)

root.mainloop()
