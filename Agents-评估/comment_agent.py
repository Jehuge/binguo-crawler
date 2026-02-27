#!/usr/bin/env python3
"""
评论分析Agent - 修复版
修复了增量保存时丢失原始评论内容的问题
支持批量并行处理，每批次自动合并原始数据并追加保存
"""
import pandas as pd
import json
import os
import time
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import ollama

# ============== 配置 ==============
DATA_DIR = ""  # 请输入数据文件所在目录，留空代表当前目录
OUTPUT_DIR = "" # 请输入结果输出目录，留空代表当前目录
MODEL_NAME = "hf.co/unsloth/Qwen3-4B-GGUF:Q6_K"  # 用户指定模型
OLLAMA_MODEL = None  # 实际调用的模型名（自动匹配）

# 并行配置 - 针对 RTX 5070 12GB 显存优化
# 4B 模型(Q6_K)约占用 3.5GB 显存，12GB 显存非常充裕，可大幅提升并发与批次
MAX_WORKERS = 6   # 5070 算力强劲，提高并行线程数榨干 GPU (建议 6-10)
BATCH_SIZE = 10   # 减小批次防止 num_ctx 截断，Qwen3 思维链会消耗额外 token (建议 10-15)

# 测试配置：限制数据条数（方便测试）
# 设为 None 则处理全部数据
MAX_COMMENTS = None  # 例如: 100, 1000, 26050, None

# ============== 提示词模板 ==============
BATCH_ANALYSIS_PROMPT = """你是一个专业的汽车评论分析助手。请批量分析以下评论，对每条评论输出6个字段。

【字段定义】
1. 有效无效：
   - 无效：纯表情符号、无意义乱码、单字或极短重复内容（如"哈哈哈"、"666"、"？"）
   - 有效：其余所有含实质内容的评论

2. 正负面：正面 / 负面 / 中性
   - 正面：对车辆、品牌、服务表达肯定、赞美、推荐
   - 负面：表达批评、抱怨、失望、质疑
   - 中性：陈述事实、提问、比较、无明显倾向

3. 营销手段：是 / 否
   - 是：含广告推广、引流二维码、软文种草、托儿水军特征、夸张宣传等
   - 否：普通用户真实评论

4. 技术亮点：是 / 否
   - 是：评论中主动描述、评价了具体技术特性（如续航、智驾、底盘、动力、能耗、空间、音响等）
   - 否：仅提问（"这车续航多少？"）、闲聊、或未涉及技术内容

5. 营销点：仅当"营销手段=是"时填写，列出评论中的营销内容要点（逗号分隔）；否则留空""

6. 技术点：仅当"技术亮点=是"时填写，列出评论提及的技术项目及简评（逗号分隔，如"智驾-体验好、续航-虚标严重"）；否则留空""

评论列表（格式：序号|评论内容）：
{comments}

【重要规则】
- 技术点、营销点必须严格来自评论原文，禁止添加原文未提及的内容
- 仅提问（如"这车续航多少？"）不算技术亮点，技术亮点=否
- 若"营销手段=否"，营销点必须为空字符串""
- 若"技术亮点=否"，技术点必须为空字符串""

请以JSON数组格式返回，每条评论对应一个对象，严格按以下格式（序号为示例，内容从原文提取）：
[
  {{"序号":N,"有效无效":"有效/无效","正负面":"正面/负面/中性","营销手段":"是/否","技术亮点":"是/否","营销点":"原文营销内容摘要或空字符串","技术点":"原文技术内容摘要或空字符串"}}
]
只返回JSON数组，不要其他内容。/no_think"""

def load_data(limit=None, source=None):
    """加载指定来源的评论数据"""
    print("="*60)
    print("正在加载数据...")
    print("="*60)
    all_data = []
    sources_info = []

    # 读取懂车帝评论
    if source is None or source == 'dongche':
        file_path = os.path.join(DATA_DIR, "懂车帝评论.xlsx")
        if os.path.exists(file_path):
            xlsx_dongche = pd.ExcelFile(file_path)
            print(f"\n[懂车帝] 共{len(xlsx_dongche.sheet_names)}个sheet:")
            for sheet in xlsx_dongche.sheet_names:
                df = xlsx_dongche.parse(sheet)
                df['车型'] = sheet.strip()
                df['来源'] = '懂车帝'
                all_data.append(df)
                print(f"   {sheet}: {len(df)} 条")
            sources_info.append(('懂车帝', len(xlsx_dongche.sheet_names)))
        else:
            print(f"\n[警告] 未找到文件: {file_path}")

    # 读取抖音评论
    if source is None or source == 'douyin':
        file_path = os.path.join(DATA_DIR, "抖音评论.xlsx")
        if os.path.exists(file_path):
            xlsx_douyin = pd.ExcelFile(file_path)
            print(f"\n[抖音] 共{len(xlsx_douyin.sheet_names)}个sheet:")
            for sheet in xlsx_douyin.sheet_names:
                df = xlsx_douyin.parse(sheet)
                df['车型'] = sheet.strip()
                df['来源'] = '抖音'
                # 清理无用列
                cols = ['昵称', '评论内容']
                if '地区' in df.columns: cols.append('地区')
                if '点赞数' in df.columns: cols.append('点赞数')
                if '评论时间' in df.columns: cols.append('评论时间')
                df = df[cols + ['车型', '来源']]
                all_data.append(df)
                print(f"   {sheet}: {len(df)} 条")
            sources_info.append(('抖音', len(xlsx_douyin.sheet_names)))
        else:
            print(f"\n[警告] 未找到文件: {file_path}")

    if not all_data:
        print("未加载到任何数据，请检查文件路径。")
        return pd.DataFrame()

    # 合并所有数据
    df = pd.concat(all_data, ignore_index=True)
    
    # 清洗评论内容
    df['评论内容'] = df['评论内容'].fillna('').astype(str).str.strip()
    # 过滤空评论
    df = df[df['评论内容'] != '']
    df = df.reset_index(drop=True)

    # 限制数据条数
    total_original = len(df)
    if limit and limit < total_original:
        df = df.head(limit)

    print(f"\n{'='*60}")
    print(f"[数据汇总]")
    for name, cnt in sources_info:
        print(f"   {name}车型: {cnt} 个")
    print(f"   原始总数: {total_original} 条")
    print(f"   实际处理: {len(df)} 条")
    if limit:
        print(f"   (已限制为前 {limit} 条)")
    print("="*60)
    return df

def batch_analyze_comments(comments_with_idx, max_retries=3):
    """
    批量分析评论 - 使用单次调用分析多条评论
    comments_with_idx: [(index, comment), ...]
    """
    # 格式化评论列表
    comments_text = "\n".join([f"{idx}|{comment[:200]}" for idx, comment in comments_with_idx])
    
    for attempt in range(max_retries):
        try:
            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[{
                    'role': 'user',
                    'content': BATCH_ANALYSIS_PROMPT.format(comments=comments_text)
                }],
                options={
                    'temperature': 0.1,
                    'num_ctx': 16384,  # 增大上下文，防止 JSON 被截断
                }
            )
            result_text = response['message']['content'].strip()
            
            # 【关键修复】剥离 Qwen3 思维链 <think>...</think> 块
            # Qwen3 是 Reasoning 模型，会先输出推理过程，再输出实际内容
            result_text = re.sub(r'<think>[\s\S]*?</think>', '', result_text).strip()
            
            # 提取JSON数组
            json_match = re.search(r'\[[\s\S]*\]', result_text)
            if json_match:
                results = json.loads(json_match.group())
                return results
            else:
                # 如果还是找不到JSON，打印前200字符用于调试
                print(f"  [调试] 未找到JSON，模型原始输出: {result_text[:200]}")
        except Exception as e:
            print(f"  批次分析失败 (尝试 {attempt+1}/{max_retries}): {e}")
            time.sleep(2)

    # 如果全部失败，返回失败标记
    return [{"序号": idx, "有效无效": "未知", "正负面": "中性", 
             "营销手段": "否", "技术亮点": "否", "营销点": "", "技术点": "分析失败"} 
            for idx, _ in comments_with_idx]

def save_incremental_csv(df_original, batch_results, source_name="全部"):
    """
    【核心修复】
    将新的一批分析结果与原始数据合并后，追加到CSV文件中
    """
    if not batch_results:
        return
        
    # 1. 将分析结果转为 DataFrame
    df_analysis = pd.DataFrame(batch_results)
    
    # 2. 根据分析结果中的'序号'，从原始 df_original 中提取对应的行
    # 注意：这里假设 df_original 的索引就是序号（我们在 load_data 中 reset_index 过了）
    target_indices = [item['序号'] for item in batch_results]
    
    # 提取原始数据的子集
    df_subset = df_original.iloc[target_indices].copy()
    
    # 确保子集里有'序号'列用于合并
    df_subset['序号'] = df_subset.index
    
    # 3. 合并：原始数据 + 分析结果
    df_merged = pd.merge(df_subset, df_analysis, on='序号', how='left')
    
    # 4. 整理列顺序（保证美观）
    cols = ['序号', '昵称', '评论内容', '来源', '车型', '评论时间', '点赞数', 
            '有效无效', '正负面', '营销手段', '技术亮点', '营销点', '技术点']
    
    # 动态插入其他可能存在的列（如地区）
    if '地区' in df_merged.columns:
        cols.insert(6, '地区')
        
    # 只保留存在的列
    final_cols = [c for c in cols if c in df_merged.columns]
    df_final = df_merged[final_cols]
    
    # 5. 追加写入 CSV
    csv_file = os.path.join(OUTPUT_DIR, f"评论分析结果_{source_name}.csv")
    file_exists = os.path.isfile(csv_file)
    
    # 如果文件不存在，写入表头；如果存在，不写表头，直接追加模式(mode='a')
    df_final.to_csv(csv_file, mode='a', header=not file_exists, index=False, encoding='utf-8-sig')

def process_parallel(df, total_workers=4, source_name="全部"):
    """并行处理评论 - 优化版（实时增量追加+合并原始数据）"""
    comments = df['评论内容'].tolist()
    total = len(comments)
    
    print(f"\n开始并行分析，共 {total} 条评论")
    print(f"使用模型: {OLLAMA_MODEL}, 并行线程: {total_workers}")
    print(f"每批处理: {BATCH_SIZE} 条")
    print(f"保存策略: 每处理完一批，立即合并原始数据并追加保存")
    print("="*60)

    # 清理旧文件，防止追加到错误的数据文件
    csv_file = os.path.join(OUTPUT_DIR, f"评论分析结果_{source_name}.csv")
    if os.path.exists(csv_file):
        try:
            os.remove(csv_file)
            print(f"已清理旧文件: {csv_file}")
        except Exception as e:
            print(f"警告: 无法清理旧文件 {csv_file}: {e}")

    # 准备批次
    batches = []
    for i in range(0, total, BATCH_SIZE):
        batch = [(i + j, comments[i + j]) for j in range(min(BATCH_SIZE, total - i))]
        batches.append(batch)
    
    print(f"共分为 {len(batches)} 个批次")

    all_results = []  
    completed = 0
    failed_batches = []
    
    start_time = time.time()

    # 使用线程池并行处理
    with ThreadPoolExecutor(max_workers=total_workers) as executor:
        future_to_batch = {executor.submit(batch_analyze_comments, batch): i 
                          for i, batch in enumerate(batches)}
        
        for future in as_completed(future_to_batch):
            batch_idx = future_to_batch[future]
            try:
                # results 是当前批次的分析结果（只有序号和分析字段）
                results = future.result()
                
                # 1. 加入内存全量列表
                all_results.extend(results)
                completed += 1
                
                # 2. 【核心修复】增量保存时传入 df (原始数据)，以便合并
                save_incremental_csv(df, results, source_name)
                
                # 进度显示
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = (len(batches) - completed) / rate if rate > 0 else 0
                
                print(f"进度: {completed}/{len(batches)} 批次 | "
                      f"已保存: {len(all_results)} 条 | "
                      f"预计剩余: {remaining/60:.1f}分钟")
                
            except Exception as e:
                print(f"批次 {batch_idx} 处理异常: {e}")
                failed_batches.append(batch_idx)

    # 处理失败的批次（串行重试）
    if failed_batches:
        print(f"\n重试失败的 {len(failed_batches)} 个批次...")
        for batch_idx in failed_batches:
            batch = batches[batch_idx]
            results = batch_analyze_comments(batch, max_retries=5)
            all_results.extend(results)
            # 重试成功也追加上去
            save_incremental_csv(df, results, source_name)

    # 按序号排序
    all_results.sort(key=lambda x: x.get('序号', 0))
    return all_results

def analyze_all_comments(df, source_name="全部"):
    """分析所有评论的主函数"""
    # 优先尝试并行处理
    try:
        results = process_parallel(df, MAX_WORKERS, source_name)
    except Exception as e:
        print(f"并行处理失败: {e}")
        print("改用串行处理...")
        
        # 串行模式也要清理文件
        csv_file = os.path.join(OUTPUT_DIR, f"评论分析结果_{source_name}.csv")
        if os.path.exists(csv_file):
            try:
                os.remove(csv_file)
            except: pass

        # 串行备用方案
        results = []
        comments = df['评论内容'].tolist()
        
        for i in range(0, len(comments), BATCH_SIZE):
            batch = [(i + j, comments[i + j]) for j in range(min(BATCH_SIZE, len(comments) - i))]
            batch_results = batch_analyze_comments(batch)
            results.extend(batch_results)
            
            # 串行模式下也立即保存（传入df）
            save_incremental_csv(df, batch_results, source_name)
            
            print(f"进度: {min(i+BATCH_SIZE, len(comments))}/{len(comments)}")
            
    return results

def save_results(df_original, results, source_name="全部"):
    """保存最终汇总结果（全量备份）"""
    print("\n" + "="*60)
    print("保存最终汇总结果...")
    print("="*60)
    
    # 创建结果DataFrame
    df_results = pd.DataFrame(results)
    
    # 合并原始数据
    df_original = df_original.copy()
    df_original['序号'] = range(len(df_original))
    
    df_output = pd.merge(df_original, df_results, left_on='序号', right_on='序号', how='left')
    
    # 重新排列列
    cols = ['序号', '昵称', '评论内容', '来源', '车型', '评论时间', '点赞数', 
            '有效无效', '正负面', '营销手段', '技术亮点', '营销点', '技术点']
    
    if '地区' in df_output.columns:
        cols.insert(6, '地区')
        
    cols = [c for c in cols if c in df_output.columns]
    df_output = df_output[cols]

    # 生成文件名
    safe_name = source_name.replace(" ", "_").replace("+", "_")
    output_file = os.path.join(OUTPUT_DIR, f"评论分析结果_{safe_name}.xlsx")
    
    # 保存 Excel
    df_output.to_excel(output_file, index=False, engine='openpyxl')
    print(f"Excel已保存: {output_file}")
    
    # 保存 CSV (全量覆盖)
    csv_file = os.path.join(OUTPUT_DIR, f"评论分析结果_{safe_name}.csv")
    df_output.to_csv(csv_file, index=False, encoding='utf-8-sig')
    print(f"CSV已保存: {csv_file}")
    
    return df_output

def generate_statistics(df_results):
    """生成统计报告"""
    print("\n" + "="*60)
    print("[统计] 分析结果统计")
    print("="*60)
    
    total = len(df_results)
    if total == 0:
        return

    # 有效无效
    print("\n[1] 有效无效分布:")
    if '有效无效' in df_results:
        valid_counts = df_results['有效无效'].value_counts()
        for k, v in valid_counts.items():
            print(f"    {k}: {v} ({v/total*100:.1f}%)")

    # 正负面
    print("\n[2] 正负面分布:")
    if '正负面' in df_results:
        sentiment_counts = df_results['正负面'].value_counts()
        for k, v in sentiment_counts.items():
            print(f"    {k}: {v} ({v/total*100:.1f}%)")

    # 营销手段
    print("\n[3] 营销手段分布:")
    if '营销手段' in df_results:
        marketing_counts = df_results['营销手段'].value_counts()
        for k, v in marketing_counts.items():
            print(f"    {k}: {v} ({v/total*100:.1f}%)")

    # 技术亮点
    print("\n[4] 技术亮点分布:")
    if '技术亮点' in df_results:
        tech_counts = df_results['技术亮点'].value_counts()
        for k, v in tech_counts.items():
            print(f"    {k}: {v} ({v/total*100:.1f}%)")
        
    # 交叉分析
    if '有效无效' in df_results and '正负面' in df_results:
        print("\n[5] 交叉分析:")
        valid_df = df_results[df_results['有效无效'] == '有效']
        print(f"  有效评论中正负面分布:")
        for k, v in valid_df['正负面'].value_counts().items():
            print(f"    {k}: {v} ({v/len(valid_df)*100:.1f}%)")

def check_ollama():
    """检查ollama状态"""
    global OLLAMA_MODEL
    print("\n" + "="*60)
    print("[检查] Ollama 状态")
    print("="*60)
    try:
        models = ollama.list()
        
        # 兼容不同版本的返回格式
        if hasattr(models, 'get'):
            model_list = models.get('models', [])
        elif hasattr(models, 'models'):
            model_list = models.models
        else:
            model_list = []
            
        available_models = []
        for m in model_list:
            name = m.get('name', m.get('model', ''))
            if name:
                available_models.append(name)
                
        if not available_models:
            print("[警告] 未找到已下载的模型")
            print(f"请运行: ollama pull {MODEL_NAME}")
            return False
            
        print(f"[OK] Ollama 服务正常运行")
        print(f"[OK] 可用模型: {available_models}")
        
        # 查找目标模型
        matched_model = None
        for m in available_models:
            if MODEL_NAME in m or m in MODEL_NAME:
                matched_model = m
                break
        
        if matched_model:
            OLLAMA_MODEL = matched_model
            print(f"[OK] 目标模型 '{MODEL_NAME}' 匹配到: {OLLAMA_MODEL}")
            return True
        else:
            print(f"\n[警告] 未找到模型 '{MODEL_NAME}'")
            print(f"请运行: ollama pull {MODEL_NAME}")
            print(f"或修改脚本中的 MODEL_NAME 为可用模型")
            return False

    except Exception as e:
        print(f"[错误] 无法连接Ollama服务: {e}")
        print("\n请确保Ollama服务已启动:")
        print("  macOS: ollama serve")
        print("  或点击Ollama应用")
        return False

def main():
    """主函数"""
    print("\n" + "="*60)
    print("[评论分析 Agent - 修复版]")
    print("="*60)
    
    # 尝试预读取文件获取数量
    dongche_count = 0
    douyin_count = 0
    try:
        f_dongche = os.path.join(DATA_DIR, "懂车帝评论.xlsx")
        if os.path.exists(f_dongche):
            xlsx = pd.ExcelFile(f_dongche)
            for sheet in xlsx.sheet_names:
                dongche_count += len(xlsx.parse(sheet))
        
        f_douyin = os.path.join(DATA_DIR, "抖音评论.xlsx")
        if os.path.exists(f_douyin):
            xlsx = pd.ExcelFile(f_douyin)
            for sheet in xlsx.sheet_names:
                douyin_count += len(xlsx.parse(sheet))
    except Exception:
        pass

    total_count = dongche_count + douyin_count

    print(f"[配置]")
    print(f"   模型: {MODEL_NAME}")
    print(f"   硬件: RTX 5070 12GB")
    print(f"   懂车帝: {dongche_count} 条")
    print(f"   抖音: {douyin_count} 条")
    print(f"   合计: {total_count} 条")
    print("="*60)

    # 交互式选择数据源
    print("\n[选择] 请选择处理数据源:")
    print("   1. 懂车帝")
    print("   2. 抖音")
    print("   3. 全部 (懂车帝 + 抖音)")
    print("   0. 退出")
    
    source_choice = input("\n请输入选项 (0-3): ").strip()
    
    source_map = {
        '1': ('dongche', dongche_count),
        '2': ('douyin', douyin_count),
        '3': (None, total_count)
    }
    
    if source_choice == '0':
        print("已退出")
        return
    elif source_choice not in source_map:
        print("无效选项")
        return
        
    source, source_total = source_map[source_choice]
    source_name = {'dongche': '懂车帝', 'douyin': '抖音', None: '全部'}[source]

    # 选择数据量
    print(f"\n[选择] {source_name}数据量:")
    print("   1. 测试 10 条")
    print("   2. 测试 50 条")
    print("   3. 测试 100 条")
    print("   4. 测试 500 条")
    print("   5. 测试 1000 条")
    print(f"   6. 全部 {source_total} 条")
    
    limit_choice = input("\n请输入选项 (1-6): ").strip()
    limit_options = {'1': 10, '2': 50, '3': 100, '4': 500, '5': 1000, '6': source_total}
    
    global MAX_COMMENTS
    MAX_COMMENTS = limit_options.get(limit_choice, source_total)
    
    print(f"\n[确认] 将处理 {source_name} 数据: {MAX_COMMENTS} 条")
    print("="*60)

    # 检查Ollama
    if not check_ollama():
        print("\n[错误] 请先启动Ollama服务")
        return

    # 加载数据
    df = load_data(limit=MAX_COMMENTS, source=source)
    
    if df.empty:
        return

    # 分析评论
    results = analyze_all_comments(df, source_name=source_name)
    
    # 保存最终结果
    df_output = save_results(df, results, source_name=source_name)
    
    # 生成统计
    generate_statistics(df_output)
    
    print("\n" + "="*60)
    print("[完成] 分析完成!")
    print("="*60)

if __name__ == "__main__":
    main()
