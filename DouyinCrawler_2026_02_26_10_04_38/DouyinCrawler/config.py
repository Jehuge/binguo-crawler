# -*- coding: utf-8 -*-
"""
抖音爬虫配置文件
"""

# Web 服务配置
PORT = 8080  # Web 服务端口
HOST = "0.0.0.0"  # 绑定地址

# 爬虫配置
HEADLESS = False  # 是否无头模式运行浏览器
SAVE_LOGIN_STATE = True  # 是否保存登录状态
USER_DATA_DIR = "browser_data/douyin_user_data_dir"  # 浏览器数据目录

# 评论爬取配置
CRAWLER_MAX_COMMENTS_COUNT = 100000  # 单个视频最大评论数

# 请求间隔配置 (防风控关键)
CRAWLER_MIN_SLEEP_SEC = 3  # 最小请求间隔（秒）
CRAWLER_MAX_SLEEP_SEC = 8  # 最大请求间隔（秒）- 随机在这个范围内选择
CRAWLER_USE_JITTER = True  # 是否添加随机抖动（强烈建议开启）
CRAWLER_JITTER_RATIO = 0.3  # 抖动比例，在基础间隔上增加 ±30% 的随机波动

# 风控处理配置
ENABLE_RISK_CONTROL_DETECTION = True  # 是否启用风控检测
RISK_CONTROL_COOLDOWN = 300  # 触发风控后的冷却时间（秒）
RISK_CONTROL_MAX_RETRIES = 3  # 风控后最大重试次数

FETCH_SUB_COMMENTS = False  # 是否获取子评论（默认关闭，风控严重）

# 数据存储配置
DATA_DIR = "data"  # 数据存储目录
