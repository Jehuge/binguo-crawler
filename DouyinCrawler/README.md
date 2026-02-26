# DouyinCrawler - 抖音视频评论爬取工具

基于 MediaCrawler 的抖音爬虫，专门用于根据关键字搜索视频并爬取评论。

## 功能特性

- 🔍 关键字搜索抖音视频
- ⭐ 支持按时间和点赞数排序
- ✅ 多选要爬取的视频
- 📥 爬取视频信息和评论
- 👀 预览爬取结果
- 📥 下载数据（支持 JSON 格式）

## 快速开始

### 1. 安装依赖

```bash
# 进入项目目录
cd DouyinCrawler

# 使用 uv 安装依赖
uv sync
```

### 2. 安装浏览器驱动

```bash
uv run playwright install
```

### 3. 启动服务

```bash
# 启动 Web 服务（默认端口 8080）
uv run python main.py

# 或使用 uvicorn
uv run uvicorn main:app --port 8080 --reload
```

### 4. 使用流程

1. 打开浏览器访问 `http://localhost:8080`
2. 输入搜索关键字
3. 选择排序方式（时间/点赞）
4. 点击搜索按钮
5. 在视频列表中勾选要爬取的视频
6. 点击"开始爬取"按钮
7. 爬取完成后可以预览数据和下载

## 配置说明

在 `config.py` 中可以修改以下配置：

- `PORT`: Web 服务端口（默认 8080）
- `HEADLESS`: 是否无头模式运行浏览器
- `SAVE_LOGIN_STATE`: 是否保存登录状态
- `CRAWLER_MAX_COMMENTS_COUNT`: 单个视频最大评论数
- `CRAWLER_MAX_SLEEP_SEC`: 请求间隔时间（秒）

## 数据存储

爬取的数据保存在 `data/` 目录下：

- `videos.json`: 视频信息
- `comments.json`: 评论数据
