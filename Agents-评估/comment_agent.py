#!/usr/bin/env python3
"""
评论分析Agent - 优化版
支持批量并行处理，提高分析效率

分析维度：有无效、正负面、营销手段、技术亮点
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
DATA_DIR = "/Users/jackjia/Desktop/demo/binguo-crawler/Agents-评估"
OUTPUT_DIR = "/Users/jackjia/Desktop/demo/binguo-crawler/Agents-评估"
MODEL_NAME = "Qwen3-4B-GGUF:Q6_K_XL"  # 用户指定模型
OLLAMA_MODEL = None  # 实际调用的模型名（自动匹配）

# 并行配置 - M3 16GB 适当调低
MAX_WORKERS = 2  # 并行线程数（内存限制）
BATCH_SIZE = 10  # 每批发送的评论数
SAVE_INTERVAL = 500  # 每处理多少条保存一次

# 测试配置：限制数据条数（方便测试）
# 设为 None 则处理全部数据
MAX_COMMENTS = None  # 例如: 100, 1000, 26050, None

# ============== 提示词模板 ==============
BATCH_ANALYSIS_PROMPT = """你是一个专业的评论分析助手。请批量分析以下汽车领域评论列表。

对每条评论，从以下四个维度进行评估：
1. 有效无效：有效/无效（无意义符号、纯表情、重复内容等为无效）
2. 正负面：正面/负面/中性
3. 营销手段：是/否（是否包含广告、推广、引流、软文等营销内容，如果是，请具体说明营销类型）
4. 技术亮点：是/否（如果是，请具体说明涉及的技术类型，如：智能驾驶、电池续航、空间设计、动力性能、底盘调校、能耗等）

评论列表（每条格式：序号|评论内容）：
{comments}

请以JSON数组格式返回结果，格式如下：
[
    {{"序号":1,"有效无效":"有效","正负面":"正面","营销手段":"否","技术亮点":"是","分析理由":"该评论提到了智能驾驶系统，体验良好，属于技术相关讨论"}},
    {{"序号":2,"有效无效":"无效","正负面":"中性","营销手段":"是","技术亮点":"否","分析理由":"该评论包含引流信息"}},
    {{"序号":3,"有效无效":"有效","正负面":"负面","营销手段":"否","技术亮点":"是","分析理由":"该评论指出续航虚标问题，属于技术层面的负面讨论"}}
]

只返回JSON数组，不要其他内容。"""


def load_data(limit=None, source=None):
    """加载指定来源的评论数据
    
    Args:
        limit: 限制数据条数，方便测试。None表示使用全部数据
        source: 数据来源 'dongche' / 'douyin' / None(全部)
    """
    print("="*60)
    print("正在加载数据...")
    print("="*60)
    
    all_data = []
    sources_info = []
    
    # 读取懂车帝评论
    if source is None or source == 'dongche':
        xlsx_dongche = pd.ExcelFile(os.path.join(DATA_DIR, "懂车帝评论.xlsx"))
        print(f"\n[懂车帝] 共{len(xlsx_dongche.sheet_names)}个sheet:")
        for sheet in xlsx_dongche.sheet_names:
            df = xlsx_dongche.parse(sheet)
            df['车型'] = sheet.strip()
            df['来源'] = '懂车帝'
            all_data.append(df)
            print(f"   {sheet}: {len(df)} 条")
        sources_info.append(('懂车帝', len(xlsx_dongche.sheet_names)))
    
    # 读取抖音评论
    if source is None or source == 'douyin':
        xlsx_douyin = pd.ExcelFile(os.path.join(DATA_DIR, "抖音评论.xlsx"))
        print(f"\n[抖音] 共{len(xlsx_douyin.sheet_names)}个sheet:")
        for sheet in xlsx_douyin.sheet_names:
            df = xlsx_douyin.parse(sheet)
            df['车型'] = sheet.strip()
            df['来源'] = '抖音'
            # 清理无用列
            cols = ['昵称', '评论内容']
            if '地区' in df.columns:
                cols.append('地区')
            if '点赞数' in df.columns:
                cols.append('点赞数')
            if '评论时间' in df.columns:
                cols.append('评论时间')
            df = df[cols + ['车型', '来源']]
            all_data.append(df)
            print(f"   {sheet}: {len(df)} 条")
        sources_info.append(('抖音', len(xlsx_douyin.sheet_names)))
    
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
                    'num_ctx': 8192,  # 更大的上下文
                }
            )
            
            result_text = response['message']['content'].strip()
            
            # 提取JSON数组
            json_match = re.search(r'\[[\s\S]*\]', result_text)
            if json_match:
                results = json.loads(json_match.group())
                return results
            
        except Exception as e:
            print(f"  批次分析失败 (尝试 {attempt+1}/{max_retries}): {e}")
            time.sleep(2)
    
    # 如果全部失败，返回失败标记
    return [{"序号": idx, "有效无效": "未知", "正负面": "中性", 
             "营销手段": "否", "技术亮点": "否", "分析理由": "分析失败"} 
            for idx, _ in comments_with_idx]


def process_parallel(df, total_workers=4, source_name="全部"):
    """并行处理评论"""
    comments = df['评论内容'].tolist()
    total = len(comments)
    
    print(f"\n开始并行分析，共 {total} 条评论")
    print(f"使用模型: {OLLAMA_MODEL}, 并行线程: {total_workers}")
    print(f"每批处理: {BATCH_SIZE} 条")
    print("="*60)
    
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
                results = future.result()
                all_results.extend(results)
                completed += 1
                
                # 每批次完成立即保存
                _save_results_immediate(all_results, source_name)
                
                # 进度显示
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = (len(batches) - completed) / rate if rate > 0 else 0
                
                print(f"进度: {completed}/{len(batches)} 批次 "
                      f"({completed*BATCH_SIZE}/{total} 条) "
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
    
    # 按序号排序
    all_results.sort(key=lambda x: x.get('序号', 0))
    
    return all_results


def _save_temp_results(results, total):
    """保存临时结果"""
    temp_file = os.path.join(OUTPUT_DIR, "分析结果_temp.csv")
    df_temp = pd.DataFrame(results)
    df_temp.to_csv(temp_file, index=False, encoding='utf-8-sig')


def _save_results_immediate(results, source_name="全部"):
    """每批次完成后立即保存结果"""
    if not results:
        return
    
    # 创建临时DataFrame用于保存
    df_temp = pd.DataFrame(results)
    
    # 生成临时文件名
    if source_name:
        temp_excel = os.path.join(OUTPUT_DIR, f"分析结果_{source_name}_temp.xlsx")
        temp_csv = os.path.join(OUTPUT_DIR, f"分析结果_{source_name}_temp.csv")
    else:
        temp_excel = os.path.join(OUTPUT_DIR, "分析结果_temp.xlsx")
        temp_csv = os.path.join(OUTPUT_DIR, "分析结果_temp.csv")
    
    df_temp.to_excel(temp_excel, index=False)
    df_temp.to_csv(temp_csv, index=False, encoding='utf-8-sig')


def analyze_all_comments(df, source_name="全部"):
    """分析所有评论的主函数"""
    # 优先尝试并行处理
    try:
        results = process_parallel(df, MAX_WORKERS, source_name)
    except Exception as e:
        print(f"并行处理失败: {e}")
        print("改用串行处理...")
        
        # 串行备用方案
        results = []
        comments = df['评论内容'].tolist()
        
        for i in range(0, len(comments), BATCH_SIZE):
            batch = [(i + j, comments[i + j]) for j in range(min(BATCH_SIZE, len(comments) - i))]
            batch_results = batch_analyze_comments(batch)
            results.extend(batch_results)
            
            # 每批次完成立即保存
            _save_results_immediate(results, source_name)
            
            print(f"进度: {min(i+BATCH_SIZE, len(comments))}/{len(comments)}")
    
    return results


def save_results(df_original, results, source_name="全部"):
    """保存分析结果
    
    Args:
        df_original: 原始评论数据
        results: 分析结果
        source_name: 数据源名称（用于文件名）
    """
    print("\n" + "="*60)
    print("保存分析结果...")
    print("="*60)
    
    # 创建结果DataFrame
    df_results = pd.DataFrame(results)
    
    # 合并原始数据
    df_original = df_original.copy()
    df_original['序号'] = range(len(df_original))
    df_output = pd.merge(df_original, df_results, left_on='序号', right_on='序号', how='left')
    
    # 重新排列列（包含车型）
    cols = ['昵称', '评论内容', '来源', '车型', '评论时间', '点赞数', 
            '有效无效', '正负面', '营销手段', '技术亮点', '分析理由']
    
    # 添加地区列（如果存在）
    if '地区' in df_output.columns:
        cols.insert(5, '地区')
    
    # 只保留存在的列
    cols = [c for c in cols if c in df_output.columns]
    df_output = df_output[cols]
    
    # 根据数据源生成文件名
    safe_name = source_name.replace(" ", "_").replace("+", "_")
    output_file = os.path.join(OUTPUT_DIR, f"评论分析结果_{safe_name}.xlsx")
    df_output.to_excel(output_file, index=False, engine='openpyxl')
    print(f"Excel已保存: {output_file}")
    
    # CSV备份
    csv_file = os.path.join(OUTPUT_DIR, f"评论分析结果_{safe_name}.csv")
    df_output.to_csv(csv_file, index=False, encoding='utf-8-sig')
    print(f"CSV已保存: {csv_file}")
    
    # 清理临时文件
    temp_file = os.path.join(OUTPUT_DIR, "分析结果_temp.csv")
    if os.path.exists(temp_file):
        os.remove(temp_file)
    
    return df_output


def generate_statistics(df_results):
    """生成统计报告"""
    print("\n" + "="*60)
    print("[统计] 分析结果统计")
    print("="*60)
    
    total = len(df_results)
    
    # 有效无效
    print("\n[1] 有效无效分布:")
    valid_counts = df_results['有效无效'].value_counts()
    for k, v in valid_counts.items():
        print(f"    {k}: {v} ({v/total*100:.1f}%)")
    
    # 正负面
    print("\n[2] 正负面分布:")
    sentiment_counts = df_results['正负面'].value_counts()
    for k, v in sentiment_counts.items():
        print(f"    {k}: {v} ({v/total*100:.1f}%)")
    
    # 营销手段
    print("\n[3] 营销手段分布:")
    marketing_counts = df_results['营销手段'].value_counts()
    for k, v in marketing_counts.items():
        print(f"    {k}: {v} ({v/total*100:.1f}%)")
    
    # 技术亮点
    print("\n[4] 技术亮点分布:")
    tech_counts = df_results['技术亮点'].value_counts()
    for k, v in tech_counts.items():
        print(f"    {k}: {v} ({v/total*100:.1f}%)")
    
    # 交叉分析
    print("\n[5] 交叉分析:")
    valid_df = df_results[df_results['有效无效'] == '有效']
    print(f"  有效评论中正负面分布:")
    for k, v in valid_df['正负面'].value_counts().items():
        print(f"    {k}: {v} ({v/len(valid_df)*100:.1f}%)")
    
    tech_df = df_results[df_results['技术亮点'] == '是']
    print(f"\n  技术相关评论正负面分布:")
    for k, v in tech_df['正负面'].value_counts().items():
        print(f"    {k}: {v} ({v/len(tech_df)*100:.1f}%)")
    
    marketing_df = df_results[df_results['营销手段'] == '是']
    print(f"\n  营销内容评论正负面分布:")
    for k, v in marketing_df['正负面'].value_counts().items():
        print(f"    {k}: {v} ({v/len(marketing_df)*100:.1f}%)")
    
    # 来源分析
    if '来源' in df_results.columns:
        print("\n[6] 按来源分析:")
        for source in df_results['来源'].unique():
            source_df = df_results[df_results['来源'] == source]
            valid_cnt = len(source_df[source_df['有效无效'] == '有效'])
            positive_cnt = len(source_df[source_df['正负面'] == '正面'])
            tech_cnt = len(source_df[source_df['技术亮点'] == '是'])
            print(f"\n  {source} (共{len(source_df)}条):")
            print(f"    有效: {valid_cnt} | 正面: {positive_cnt} | 技术: {tech_cnt}")
    
    # 车型分析
    if '车型' in df_results.columns:
        print("\n[7] 按车型分析:")
        for car in df_results['车型'].unique():
            car_df = df_results[df_results['车型'] == car]
            valid_cnt = len(car_df[car_df['有效无效'] == '有效'])
            positive_cnt = len(car_df[car_df['正负面'] == '正面'])
            tech_cnt = len(car_df[car_df['技术亮点'] == '是'])
            print(f"  {car}: {len(car_df)}条, 有效:{valid_cnt}, 正面:{positive_cnt}, 技术:{tech_cnt}")


def check_ollama():
    """检查ollama状态"""
    global OLLAMA_MODEL
    print("\n" + "="*60)
    print("[检查] Ollama 状态")
    print("="*60)
    
    try:
        # 尝试列出模型
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
        
        # 查找目标模型（支持简写或全称匹配）
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
    # 先检查数据总量
    print("\n" + "="*60)
    print("[评论分析 Agent]")
    print("="*60)
    
    # 获取各数据源总量
    xlsx_dongche = pd.ExcelFile(os.path.join(DATA_DIR, "懂车帝评论.xlsx"))
    dongche_count = 0
    for sheet in xlsx_dongche.sheet_names:
        df = xlsx_dongche.parse(sheet)
        dongche_count += len(df[df['评论内容'].fillna('').astype(str).str.strip() != ''])
    
    xlsx_douyin = pd.ExcelFile(os.path.join(DATA_DIR, "抖音评论.xlsx"))
    douyin_count = 0
    for sheet in xlsx_douyin.sheet_names:
        df = xlsx_douyin.parse(sheet)
        douyin_count += len(df[df['评论内容'].fillna('').astype(str).str.strip() != ''])
    
    total_count = dongche_count + douyin_count
    
    print(f"[配置]")
    print(f"   模型: {MODEL_NAME}")
    print(f"   硬件: M3 Mac 16GB")
    print(f"   懂车帝: {dongche_count} 条")
    print(f"   抖音: {douyin_count} 条")
    print(f"   合计: {total_count} 条")
    print(f"   分析维度: 有效无效, 正负面, 营销手段, 技术亮点")
    print("="*60)
    
    # 交互式选择数据源和数据量
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
    
    limit_options = {
        '1': 10,
        '2': 50,
        '3': 100,
        '4': 500,
        '5': 1000,
        '6': source_total
    }
    
    MAX_COMMENTS = limit_options.get(limit_choice, source_total)
    
    print(f"\n[确认] 将处理 {source_name} 数据: {MAX_COMMENTS} 条")
    print("="*60)
    
    # 检查Ollama
    if not check_ollama():
        print("\n[错误] 请先启动Ollama服务")
        return
    
    # 加载指定数据源
    df = load_data(limit=MAX_COMMENTS, source=source)
    
    # 分析评论
    results = analyze_all_comments(df, source_name=source_name)
    
    # 保存结果（分开保存）
    df_output = save_results(df, results, source_name=source_name)
    
    # 生成统计
    generate_statistics(df_output)
    
    print("\n" + "="*60)
    print("[完成] 分析完成!")
    print("="*60)


if __name__ == "__main__":
    main()
