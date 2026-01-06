"""
templates.py - 自然语言报告生成模板库

功能: 将原始元数据转换为训练 MLLM 的自然语言对话数据
支持: 视觉类 Bug（当前）+ 交互类 Bug（未来）
"""

import json
import os
from typing import Dict, List, Any

# ===================== 视觉类 Bug 模板 =====================

VISUAL_BUG_TEMPLATES = {
    "Layout_Overlap": {
        "detection": [
            "检测到布局重叠缺陷：{element_desc}在坐标({x}, {y})位置与周围内容发生遮挡。",
            "发现元素重叠问题：{element_desc}的定位异常，与相邻元素产生视觉重叠。",
            "UI 布局错误：页面中的{element_desc}元素位置偏移，导致与其他内容重叠，影响可读性。"
        ],
        "impact": "影响用户体验，导致内容难以阅读或交互受阻。",
        "suggestion": "建议检查该元素的 CSS 定位属性（transform/position），确保不与其他元素产生遮挡。"
    },
    
    "Element_Missing": {
        "detection": [
            "检测到元素缺失：{element_desc}在页面中应当可见但未正常显示。",
            "发现视觉缺陷：预期在({x}, {y})位置的{element_desc}元素不可见。",
            "UI 渲染异常：{element_desc}元素未能正确渲染，可能因 CSS visibility 或 display 属性错误。"
        ],
        "impact": "关键元素不可见，用户无法完成预期操作。",
        "suggestion": "检查元素的 visibility、display、opacity 属性，确保元素正确显示。"
    },
    
    "Text_Overflow": {
        "detection": [
            "检测到文本溢出：{element_desc}中的文本内容超出容器边界。",
            "发现文本截断问题：{element_desc}的文本未正确换行，导致内容被裁切。",
            "UI 文本渲染异常：{element_desc}的文本内容溢出，影响布局美观性。"
        ],
        "impact": "文本内容不完整，用户无法获取全部信息。",
        "suggestion": "建议为容器设置合适的 overflow 或 text-overflow 属性，或调整宽度限制。"
    },
    
    "Broken_Image": {
        "detection": [
            "检测到图片加载失败：{element_desc}在坐标({x}, {y})位置显示为破损图标。",
            "发现资源加载错误：页面中的图片元素（{element_desc}）无法正常加载。",
            "UI 媒体缺陷：{element_desc}图片资源缺失或路径错误。"
        ],
        "impact": "图片无法显示，影响页面完整性和用户体验。",
        "suggestion": "检查图片资源路径是否正确，确保服务器资源可访问。"
    },
    
    "Layout_Alignment": {
        "detection": [
            "检测到对齐错误：{element_desc}的对齐方式异常，与设计规范不符。",
            "发现布局对齐缺陷：{element_desc}的 text-align 或 align-items 属性设置不当。",
            "UI 对齐异常：{element_desc}元素未按预期对齐，影响视觉一致性。"
        ],
        "impact": "页面布局不整齐，降低专业性和可读性。",
        "suggestion": "检查对齐相关的 CSS 属性（text-align, justify-content, align-items）。"
    },
    
    "Layout_Spacing": {
        "detection": [
            "检测到间距异常：{element_desc}的 margin 或 padding 设置不一致。",
            "发现布局间距缺陷：{element_desc}与相邻元素的间距过大或过小。",
            "UI 间距错误：{element_desc}的外边距/内边距配置不符合设计规范。"
        ],
        "impact": "页面布局不协调，影响视觉美观。",
        "suggestion": "统一调整元素的 margin 和 padding 值，确保间距一致性。"
    },
    
    "Data_Format_Error": {
        "detection": [
            "检测到数据格式错误：{element_desc}中显示的数据格式不正确（如日期、数字格式）。",
            "发现数据展示缺陷：{element_desc}的内容格式异常，可能导致用户误解。",
            "UI 数据异常：{element_desc}显示的数据未经正确格式化处理。"
        ],
        "impact": "用户难以理解或信任显示的数据。",
        "suggestion": "检查数据处理逻辑，确保使用正确的格式化函数（如 toLocaleString）。"
    },
    
    "Style_Color_Contrast": {
        "detection": [
            "检测到对比度不足：{element_desc}的文字颜色与背景色对比度过低，难以阅读。",
            "发现无障碍缺陷：{element_desc}不符合 WCAG 对比度标准（建议 ≥ 4.5:1）。",
            "UI 可访问性问题：{element_desc}的颜色配置不利于视觉障碍用户阅读。"
        ],
        "impact": "降低可读性，不符合无障碍访问标准。",
        "suggestion": "调整文字或背景颜色，确保对比度满足 WCAG AA 标准（4.5:1）。"
    },
    
    "Style_Size_Inconsistent": {
        "detection": [
            "检测到尺寸不一致：{element_desc}的字体大小或宽度与同类元素不匹配。",
            "发现视觉不一致性：{element_desc}的尺寸配置异常，破坏页面统一性。",
            "UI 样式缺陷：{element_desc}的大小设置不符合设计系统规范。"
        ],
        "impact": "页面视觉不统一，降低用户信任感。",
        "suggestion": "使用设计系统的标准尺寸变量，确保同类元素样式一致。"
    }
}

# ===================== 核心函数 =====================

def generate_visual_report(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    从原始元数据生成视觉类 Bug 的自然语言报告
    
    Args:
        metadata: 从 raw_metadata/{uuid}.json 读取的数据
    
    Returns:
        适用于 SFT 训练的对话格式数据
    """
    bug_type = metadata.get("bug_type", "Unknown")
    bbox = metadata.get("bbox_before", {})
    
    # 生成元素描述
    element_desc = _generate_element_description(metadata)
    
    # 获取模板
    template = VISUAL_BUG_TEMPLATES.get(bug_type)
    if not template:
        return _generate_fallback_report(metadata)
    
    # 随机选择一个检测描述（增加多样性）
    import random
    detection = random.choice(template["detection"]).format(
        element_desc=element_desc,
        x=int(bbox.get("x", 0)),
        y=int(bbox.get("y", 0))
    )
    
    # 组装完整报告
    full_report = f"{detection}\n\n{template['impact']}\n\n{template['suggestion']}"
    
    # 构建 SFT 对话格式
    conversation = {
        "id": metadata.get("id"),
        "image": f"images/visual/{metadata['id']}_buggy.png",
        "conversations": [
            {
                "from": "human",
                "value": "请分析这个网页截图，判断是否存在 UI 缺陷，并给出详细的问题描述。"
            },
            {
                "from": "assistant",
                "value": full_report
            }
        ],
        "metadata": {
            "bug_type": bug_type,
            "url": metadata.get("url"),
            "bbox": bbox,
            "diff_score": metadata.get("diff_score")
        }
    }
    
    return conversation


def _generate_element_description(metadata: Dict[str, Any]) -> str:
    """生成元素的自然语言描述"""
    # 这里可以从元数据中提取元素信息
    # 当前版本简化处理，未来可扩展
    bug_type = metadata.get("bug_type")
    
    # 根据 bug 类型推断可能的元素
    element_hints = {
        "Layout_Overlap": "导航栏按钮",
        "Element_Missing": "提交按钮",
        "Text_Overflow": "标题文本",
        "Broken_Image": "产品图片",
        "Layout_Alignment": "列表项",
        "Layout_Spacing": "卡片元素",
        "Data_Format_Error": "日期字段",
        "Style_Color_Contrast": "链接文本",
        "Style_Size_Inconsistent": "标题元素"
    }
    
    return element_hints.get(bug_type, "页面元素")


def _generate_fallback_report(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """未知 Bug 类型的回退报告"""
    return {
        "id": metadata.get("id"),
        "image": f"images/visual/{metadata['id']}_buggy.png",
        "conversations": [
            {
                "from": "human",
                "value": "请分析这个网页截图，判断是否存在 UI 缺陷。"
            },
            {
                "from": "assistant",
                "value": f"检测到 UI 异常：{metadata.get('bug_type', 'Unknown')} 类型缺陷。"
            }
        ]
    }


# ===================== 批量处理 =====================

def process_all_metadata(raw_metadata_dir: str, output_jsonl: str):
    """
    批量处理所有原始元数据，生成训练数据
    
    Args:
        raw_metadata_dir: raw_metadata/ 目录路径
        output_jsonl: 输出的 JSONL 文件路径（如 train_sft.jsonl）
    """
    results = []
    
    # 遍历所有 JSON 文件
    for filename in os.listdir(raw_metadata_dir):
        if not filename.endswith(".json"):
            continue
        
        filepath = os.path.join(raw_metadata_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        
        # 生成报告
        conversation = generate_visual_report(metadata)
        results.append(conversation)
    
    # 写入 JSONL 文件（每行一个 JSON）
    with open(output_jsonl, "w", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    
    print(f"✅ 已生成 {len(results)} 条训练数据 → {output_jsonl}")


# ===================== 命令行接口 =====================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法:")
        print("  python templates.py generate    # 批量生成训练数据")
        print("  python templates.py test <uuid> # 测试单个样本")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "generate":
        # 批量生成训练数据
        raw_dir = "dataset_injected/raw_metadata"
        output_train = "dataset_injected/training_data/train_sft.jsonl"
        
        if not os.path.exists(raw_dir):
            print(f"❌ 错误: {raw_dir} 目录不存在")
            sys.exit(1)
        
        process_all_metadata(raw_dir, output_train)
        print(f"✅ 训练数据已保存到 {output_train}")
    
    elif command == "test":
        # 测试单个样本
        if len(sys.argv) < 3:
            print("❌ 错误: 请提供 UUID")
            sys.exit(1)
        
        uuid = sys.argv[2]
        metadata_path = f"dataset_injected/raw_metadata/{uuid}.json"
        
        if not os.path.exists(metadata_path):
            print(f"❌ 错误: {metadata_path} 不存在")
            sys.exit(1)
        
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        
        result = generate_visual_report(metadata)
        print("\n" + "="*60)
        print("生成的对话数据:")
        print("="*60)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    else:
        print(f"❌ 未知命令: {command}")
        sys.exit(1)
