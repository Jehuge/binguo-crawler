#!/usr/bin/env python3
"""
快速测试脚本 - 验证Agent配置是否正确
仅分析10条评论，用于测试
"""

import ollama
import pandas as pd
import os
import json

# 配置
DATA_DIR = "/Users/jackjia/Desktop/demo/binguo-crawler/Agents-评估"
MODEL_NAME = "Qwen3-4B-GGUF:Q6_K_XL"  # 用户指定模型

# 测试提示词
TEST_PROMPT = """分析以下汽车评论，从四个维度评估：
1. 有效无效：有效/无效
2. 正负面：正面/负面/中性
3. 营销手段：是/否
4. 技术亮点：是/否

评论：{comment}

请以JSON格式返回：{{"有效无效":"","正负面":"","营销手段":"","技术亮点":"","分析理由":""}}
只返回JSON。"""


def check_ollama():
    """检查Ollama"""
    print("="*50)
    print("1. 检查Ollama服务")
    print("="*50)
    
    try:
        models = ollama.list()
        model_list = [m['name'] for m in models.get('models', [])]
        print(f"✓ Ollama正常运行")
        print(f"  可用模型: {model_list}")
        
        if any(MODEL_NAME in m for m in model_list):
            print(f"✓ 目标模型 {MODEL_NAME} 可用")
            return True
        else:
            print(f"✗ 未找到模型 {MODEL_NAME}")
            print(f"  请运行: ollama pull {MODEL_NAME}")
            return False
    except Exception as e:
        print(f"✗ Ollama连接失败: {e}")
        print("  请先启动: ollama serve")
        return False


def test_model():
    """测试模型"""
    print("\n" + "="*50)
    print("2. 测试模型推理")
    print("="*50)
    
    test_comment = "这车的智驾系统太牛了，华为技术就是强！"
    
    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[{
                'role': 'user',
                'content': TEST_PROMPT.format(comment=test_comment)
            }],
            options={'temperature': 0.1}
        )
        
        result = response['message']['content'].strip()
        print(f"测试评论: {test_comment}")
        print(f"模型输出: {result}")
        
        # 尝试解析JSON
        import re
        json_match = re.search(r'\{[\s\S]*\}', result)
        if json_match:
            parsed = json.loads(json_match.group())
            print(f"✓ JSON解析成功")
            print(f"  有效无效: {parsed.get('有效无效')}")
            print(f"  正负面: {parsed.get('正负面')}")
            print(f"  营销手段: {parsed.get('营销手段')}")
            print(f"  技术亮点: {parsed.get('技术亮点')}")
            return True
        else:
            print("✗ 无法解析JSON")
            return False
            
    except Exception as e:
        print(f"✗ 模型测试失败: {e}")
        return False


def check_data():
    """检查数据文件"""
    print("\n" + "="*50)
    print("3. 检查数据文件")
    print("="*50)
    
    files = ['懂车帝评论.xlsx', '抖音评论.xlsx']
    total = 0
    
    for f in files:
        path = os.path.join(DATA_DIR, f)
        if os.path.exists(path):
            df = pd.read_excel(path)
            print(f"✓ {f}: {len(df)} 条")
            total += len(df)
        else:
            print(f"✗ {f}: 文件不存在")
    
    print(f"\n总计: {total} 条评论")
    return total > 0


def main():
    """主函数"""
    print("\n" + "="*50)
    print("🚗 评论分析Agent - 系统测试")
    print("="*50)
    
    results = []
    
    # 1. 检查Ollama
    results.append(("Ollama服务", check_ollama()))
    
    # 2. 测试模型
    if results[-1][1]:
        results.append(("模型推理", test_model()))
    else:
        results.append(("模型推理", False))
    
    # 3. 检查数据
    results.append(("数据文件", check_data()))
    
    # 总结
    print("\n" + "="*50)
    print("测试结果汇总")
    print("="*50)
    
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {name}: {status}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "="*50)
    if all_passed:
        print("✅ 所有测试通过！可以运行主程序：")
        print("   python comment_agent.py")
    else:
        print("⚠️ 部分测试失败，请先修复后再运行")
    print("="*50)


if __name__ == "__main__":
    main()
