# Awesome Spider 爬虫集合

本项目集合了懂车帝、今日头条、腾讯新闻、汽车之家、易车网等平台的爬虫脚本，既可以通过 GUI 操作，也可以在命令行中以脚本方式调用。结合最新的风控与结构调研，我们已经为每个站点挑选出最可靠的单一采集方式，并停止维护另一种方案：

| 站点 | 推荐模式 | 主要原因 |
| --- | --- | --- |
| 懂车帝 | HTML 解析 + 浏览器行为模拟 | 页面以短视频/车评为主，内容动态加载且滑块校验频繁，必须依赖浏览器真实交互。 |
| 今日头条 | HTML 解析（undetected-chromedriver） | 综合资讯频繁更新，风控比懂车帝更严格（账号、设备指纹等），通过浏览器持久化 cookies 更稳。 |
| 腾讯新闻 | 官方/半官方 JSON API | 新闻接口开放、风险低，直接调用 `i.news.qq.com` 接口即可稳定获取大量资讯。 |
| 汽车之家 | JSON API | 文章/帖子多为静态资源，公开搜索接口就能拿到完整结构化数据。 |
| 易车网 | JSON API | 官方频道提供搜索接口，反爬较弱，直接请求即可。 |

## 目录结构

```text
awesome-spider/
├── gui.py                 # Tkinter GUI 程序
├── requiredments.txt      # Python 依赖列表（注意：文件名为 requiredments）
├── scripts/               # 各站点快速爬虫脚本
├── spiders/               # 各站点爬虫实现
│   ├── autohome_spider.py
│   ├── base_spider.py
│   ├── dcd_spider.py
│   ├── tencent_spider.py
│   ├── toutiao_spider.py
│   └── yiche_spider.py
└── util/                  # 常用脚本工具（合并csv文件，csv 转 json等）
```

## 环境准备

### 1. 安装 Python 依赖

建议使用 Python 3.11 及以上版本。先创建虚拟环境（可选）：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows 下使用 .venv\Scripts\activate
```

然后安装依赖：

```bash
pip install -r requiredments.txt
```

> ⚠️ 依赖文件名为 `requiredments.txt`（非标准拼写），请确认安装命令指向正确的文件。

### 2. 准备 Chrome 与 Chromedriver

HTML 解析模式依赖本地 Chrome 浏览器与匹配版本的 Chromedriver：

1. 确认已安装 Chrome（或 Chromium / Edge），记录其可执行文件路径，例如：
   - Windows: `C:\Program Files\Google\Chrome\Application\chrome.exe`
   - macOS: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
   - Linux: `/usr/bin/google-chrome`
2. 下载与浏览器版本匹配的 Chromedriver，并记录 driver 可执行文件路径。

### 3. 配置 `.env`

在项目根目录创建 `.env` 文件，填入如下内容（按需调整）：

```ini
# Chrome 浏览器与驱动路径
CHROME_BINARY_PATH="C:/Program Files/Google/Chrome/Application/chrome.exe"
CHROMEDRIVER_PATH="C:/Drivers/chromedriver.exe"

# 今日头条搜索入口，必须包含 KEYWORD 占位符
TOUTIAO_SEARCH_URL="https://www.toutiao.com/search/?keyword=KEYWORD&source=input"

# GUI 默认关键词，逗号分隔
KEYWORDS="沃尔沃"

# 可选：请求间隔、翻页参数等自定义变量
PAGE_SLEEP_TIME=3
```

> - `CHROME_BINARY_PATH` 与 `CHROMEDRIVER_PATH` 是 HTML 解析模式必备配置。
> - `TOUTIAO_SEARCH_URL` 用于构建今日头条搜索页，必须包含 `KEYWORD` 字符串。
> - 如果需要使用懂车帝滑块绕过脚本（HTML 模式），首次运行会弹出浏览器要求手动完成验证，随后自动保存 `cookies.json`，下次可直接复用。

## 运行方式

### GUI 操作

```bash
python gui.py
```

界面加载 `.env` 中的 `KEYWORDS` 列表，可选择站点与关键词并批量抓取；程序会自动匹配每个站点的推荐模式，并将结果保存在 `output/站点_关键词_模式.csv`。

### 脚本调用示例

下面示例展示如何在命令行或自定义脚本中调用各爬虫。所有爬虫的 `crawl` 方法都会返回一个标准化的字典列表：

```python
{
    "site_name": "站点名称",
    "advertiser": "关键词/广告主",
    "title": "标题",
    "url": "详情链接",
    "date": "发布日期（若可获取）"
}
```

#### 1. 懂车帝（Dongchedi） — 推荐：HTML 解析

懂车帝的搜索结果主要以短视频与图文卡片形式动态加载，并会频繁触发滑块/行为验证码。项目统一通过 Chromedriver + cookies 复用的方式模拟真实用户浏览：

```python
from spiders.dcd_spider import DcdSpider

spider = DcdSpider()
results = spider.crawl("沃尔沃", max_pages=1)
```

> - 内置 `util.dcd_browser.load_driver_with_cookies` 会注入人工处理后的 cookies。
> - 建议翻页之间保持 5~10 秒间隔，并配合代理池降低封禁风险。

#### 2. 今日头条（Toutiao） — 推荐：HTML 解析（undetected-chromedriver）

今日头条的接口风控严格（登录态、指纹、IP），相比之下保持浏览器会话的 HTML 解析更稳定：

```python
from spiders.toutiao_spider import ToutiaoSpider

spider = ToutiaoSpider()
results = spider.crawl("新能源", max_pages=5)
```

> - 需要在 `.env` 中配置 `TOUTIAO_SEARCH_URL`，并提前完成一次滑块验证以便持久化 cookies。
> - 运行时会自动模拟滚动加载，建议结合代理和限速策略。

#### 3. 腾讯新闻（Tencent News） — 推荐：官方 JSON API

腾讯新闻提供的 `i.news.qq.com` 搜索接口开放度高、稳定性佳，直接调用即可快速获取资讯列表：

```python
from spiders.tencent_spider import TencentSpider

spider = TencentSpider()
results = spider.crawl("极氪", time_slices=["9月", "8月"], max_pages=5)
```

> - 可按需调整 `time_slices` 与 `max_pages` 以控制抓取范围。

#### 4. 汽车之家（Autohome） — 推荐：JSON API

汽车之家开放的搜索接口结构清晰、返回字段齐全，直接调用即可批量获取文章或帖子数据：

```python
from spiders.autohome_spider import AutohomeSpider

spider = AutohomeSpider()
results = spider.crawl("比亚迪", max_pages=5)
```

#### 5. 易车网（YiChe） — 推荐：JSON API

易车新闻/视频频道都提供了公开 API，方便一次性抓取多频道资讯：

```python
from spiders.yiche_spider import YiCheSpider

spider = YiCheSpider(keyword="理想汽车", max_pages=2)
news = spider.fetch_news()
videos = spider.fetch_videos()
```

### 快速调试脚本（`scripts/`）

为了方便快速验证推荐的采集方式，项目根目录提供了 5 个站点共 6 个示例脚本（关键词默认“沃尔沃”）。所有脚本运行结束后会自动将结果保存到 `output/csv/站点_关键词_时间范围.csv`，日期字段统一格式化为 `yyyy-mm-dd`，便于后续汇总分析。

| 站点 | 推荐模式 | 命令示例 | 说明 |
| --- | --- | --- | --- |
| 懂车帝 | HTML | `python scripts/dcd_html_volvo.py` | 通过 Chromedriver 渲染页面并模拟滚动加载 |
| 今日头条 | HTML | `python scripts/toutiao_html_volvo.py` | 使用 undetected-chromedriver 打开搜索页并提取数据 |
| 腾讯新闻 | JSON API | `python scripts/tencent_api_volvo.py` | 循环时间切片访问官方搜索接口（可加 `--time-slices` 调整） |
| 汽车之家 | JSON API | `python scripts/autohome_api_volvo.py` | 请求 `sou.api.autohome.com.cn/v1/search` 接口 |
| 易车网 | JSON API（新闻） | `python scripts/yiche_news_volvo.py` | 调用公开接口抓取新闻频道搜索结果 |
| 易车网 | JSON API（视频） | `python scripts/yiche_video_volvo.py` | 调用公开接口抓取视频频道搜索结果 |

所有脚本默认关键词均为“沃尔沃”，可通过 `--keyword` 参数覆盖。脚本共用一套 CLI 选项：

- `--time-range`：用于描述当前抓取的时间范围（默认“全部时间”），同时参与 CSV 文件名生成；
- `--output-dir`：CSV 输出目录，默认为 `output/csv`；
- `--preview`：控制终端预览的条数（默认为 5，设为 0 可关闭预览）；
- `--json`：若指定路径，则额外保存同名 JSON 文件。

示例：

```bash
# 指定翻页次数、预览数量，并保存为 JSON
python scripts/dcd_html_volvo.py --keyword="极氪" --max-pages=5 --preview=10 --json=output/dcd_html_jik.json

# 腾讯新闻 API 模式指定自定义时间切片
python scripts/tencent_api_volvo.py --time-slices="9月,8月"
```

所有 CSV 均通过 `util.helpers.save_to_csv` 写入磁盘，若目标文件已存在会自动追加记录并确保 UTF-8 BOM 编码。

### 数据导出

若需在自定义脚本中复用导出逻辑，可直接调用 `util.helpers.save_to_csv` 并传入由爬虫返回的标准化结果。工具会在写入时补齐 `site_name`、`advertiser`、`title`、`url` 字段并将 `date` 格式化为 `yyyy-mm-dd`：

```python
from util.save_to_csv import save_to_csv

save_to_csv(results, filename="output/dongchedi_volvo.csv")
```

若需要合并多个 CSV，可运行 `python util/merge_csv.py`（按脚本内提示操作）。

## 常见问题

1. **Chromedriver 版本不匹配**：请确保 driver 版本与 Chrome 主版本一致，或使用 `undetected-chromedriver` 自动适配（仅今日头条 HTML 模式使用）。
2. **第一次运行懂车帝 HTML 模式提示滑块验证**：按照命令行提示在弹出的浏览器中完成验证，脚本会自动保存 cookies。
3. **接口返回为空或被限流**：适当增大 `max_pages` 之间的 `time.sleep`，或缩小并发关键词数量。
4. **需要拓展新的字段/站点**：参考 `spiders/base_spider.py` 的规范输出，自定义字段可在 CSV 合并时追加列。

欢迎在此基础上继续扩展更多站点或补充 CLI/调度功能。
