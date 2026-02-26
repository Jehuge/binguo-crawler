# 评论分析Agent

基于 Ollama 本地 Qwen 模型，自动分析汽车领域评论数据。

## 分析维度

| 维度 | 说明 |
|------|------|
| 有效无效 | 判断评论是否有实质内容（无意义符号、纯表情、重复内容等为无效） |
| 正负面 | 正面评价、负面评价或中性讨论 |
| 营销手段 | 是否包含广告、推广、引流等营销内容 |
| 技术亮点 | 是否涉及车辆技术、性能、配置等专业讨论 |

## 数据来源

- **懂车帝评论.xlsx** - 4个车型（问界M9、理想L9、吉利M9、零跑C16）
- **抖音评论.xlsx** - 4个车型（问界M9、理想L9、领跑C16、吉利M9）

## 使用方法

### 1. 启动 Ollama 服务

```bash
# 方式1: 命令行启动
ollama serve

# 方式2: macOS点击Ollama应用
```

### 2. 下载模型（如需要）

```bash
# 用户指定模型
ollama run Qwen3-4B-GGUF:Q6_K_XL
```

### 3. 安装依赖并运行

```bash
cd /Users/jackjia/Desktop/demo/binguo-crawler/Agents-评估

# 使用 uv（推荐）
uv sync
uv run python test_agent.py    # 先测试
uv run python comment_agent.py # 运行分析

# 或使用 pip
pip install -r requirements.txt
python test_agent.py
python comment_agent.py
```

## 输出文件

- `评论分析结果.xlsx` - 完整分析结果
- `评论分析结果.csv` - CSV备份

## 配置参数

在 `comment_agent.py` 中调整：

```python
MODEL_NAME = "Qwen3-4B-GGUF:Q6_K_XL"  # 使用的模型
MAX_WORKERS = 2                        # 并行线程数（M3 16GB）
BATCH_SIZE = 10                        # 每批处理评论数
```

## 硬件配置

- Mac M3, 16GB RAM
- 约14万条评论
- 预计运行时间：2-3小时
