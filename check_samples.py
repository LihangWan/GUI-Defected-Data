#!/usr/bin/env python3
"""
检查生成的样本质量和bug注入成功率
验证:
  1. 图片是否正确保存
  2. 红标是否正确显示
  3. 元数据是否完整
  4. bug注入是否成功
"""

import os
import json
from pathlib import Path
from PIL import Image
from collections import defaultdict


def check_images():
    """检查图片文件"""
    print("\n📸 图片检查")
    print("="*70)
    
    img_dir = "dataset_injected/images/interaction"
    if not os.path.exists(img_dir):
        print("[-] 图片目录不存在")
        return False
    
    images = list(Path(img_dir).glob("*.png"))
    if not images:
        print("[-] 没有找到图片文件")
        return False
    
    print(f"[+] 找到 {len(images)} 张图片\n")
    
    # 按样本ID分组
    samples = defaultdict(list)
    for img in images:
        name = img.stem
        # int_xxx_start.png, int_xxx_action.png, int_xxx_end.png
        parts = name.rsplit("_", 1)
        if len(parts) == 2:
            sample_id = parts[0]
            frame_type = parts[1]
            samples[sample_id].append(frame_type)
    
    print("样本检查:")
    for sample_id in sorted(samples.keys()):
        frames = sorted(samples[sample_id])
        complete = set(frames) == {"start", "action", "end"}
        status = "✓" if complete else "✗"
        missing = [f for f in ["start", "action", "end"] if f not in frames]
        msg = f"缺失: {', '.join(missing)}" if missing else "完整"
        print(f"  {status} {sample_id}: {msg}")
        
        # 检查红标 - 查看action图
        if "action" in frames:
            img_path = os.path.join(img_dir, f"{sample_id}_action.png")
            try:
                img = Image.open(img_path)
                # 检查右上角是否有红色像素
                width, height = img.size
                # 从右上角取样(200x50像素范围)
                sample_box = (width - 200, 0, width, 50)
                crop = img.crop(sample_box)
                pixels = list(crop.getdata())
                
                red_count = 0
                for pixel in pixels:
                    if len(pixel) >= 3:
                        r, g, b = pixel[0], pixel[1], pixel[2]
                        # 红色像素: R > 200, G < 100, B < 100
                        if r > 200 and g < 100 and b < 100:
                            red_count += 1
                
                if red_count > 100:  # 至少100个红色像素
                    print(f"       [✓] 红标检测: 找到 {red_count} 个红色像素")
                else:
                    print(f"       [✗] 红标检测: 只找到 {red_count} 个红色像素（期望 > 100）")
            except Exception as e:
                print(f"       [!] 无法分析图片: {e}")
    
    return len(samples) > 0


def check_metadata():
    """检查元数据完整性"""
    print("\n📋 元数据检查")
    print("="*70)
    
    meta_dir = "dataset_injected/raw_metadata"
    if not os.path.exists(meta_dir):
        print("[-] 元数据目录不存在")
        return False
    
    files = [f for f in os.listdir(meta_dir) if f.startswith("int_") and f.endswith(".json")]
    if not files:
        print("[-] 没有找到元数据文件")
        return False
    
    print(f"[+] 找到 {len(files)} 个元数据文件\n")
    
    required_keys = {
        "id", "bug_type", "bug_class", "description", 
        "url", "element_semantic", "action_trace", "images",
        "injection_verified", "timestamp"
    }
    
    stats = {
        "complete": 0,
        "incomplete": 0,
        "bug_types": defaultdict(int),
        "verification": defaultdict(int),
    }
    
    for filename in sorted(files)[:10]:  # 检查前10个
        meta_path = os.path.join(meta_dir, filename)
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            
            bug_type = meta.get("bug_type", "Unknown")
            is_verified = meta.get("injection_verified", False)
            
            stats["bug_types"][bug_type] += 1
            stats["verification"][is_verified] += 1
            
            missing_keys = required_keys - set(meta.keys())
            if not missing_keys:
                stats["complete"] += 1
                status = "✓"
            else:
                stats["incomplete"] += 1
                status = "✗"
            
            verification_status = "✓ 已验证" if is_verified else "? 未验证"
            print(f"  {status} {filename}")
            print(f"       Bug: {bug_type:25} {verification_status}")
            
            if missing_keys:
                print(f"       缺失字段: {', '.join(missing_keys)}")
                
            # 检查图片引用
            images = meta.get("images", {})
            img_refs = [v for v in images.values() if v]
            if len(img_refs) == 3:
                print(f"       图片: ✓ 3张完整")
            else:
                print(f"       图片: ✗ 只有 {len(img_refs)} 张")
            
            print()
        except Exception as e:
            print(f"  [!] {filename}: {e}\n")
    
    print("="*70)
    print(f"✅ 完整度: {stats['complete']}/{len(files[:10])}")
    print(f"\n📊 Bug类型分布:")
    for bug_type, count in sorted(stats["bug_types"].items()):
        print(f"  • {bug_type}: {count}")
    
    print(f"\n🔍 验证状态:")
    total_verified = stats["verification"][True]
    total = sum(stats["verification"].values())
    print(f"  • 已验证: {total_verified}/{total}")
    print(f"  • 验证率: {100*total_verified/total:.1f}%")
    
    print(f"\n💡 说明:")
    print(f"  • Navigation_Error/Validation_Error: 自动验证")
    print(f"  • 其他类型: 拦截器注入后即验证（不要求网络日志）")
    print(f"  • 某些元素（如按钮）可能不触发网络请求，这是正常的")
    
    return len(files) > 0


def check_bug_injection():
    """检查bug注入质量"""
    print("\n🐛 Bug注入质量检查")
    print("="*70)
    
    meta_dir = "dataset_injected/raw_metadata"
    if not os.path.exists(meta_dir):
        print("[-] 元数据目录不存在")
        return
    
    files = [f for f in os.listdir(meta_dir) if f.startswith("int_") and f.endswith(".json")]
    
    quality_checks = {
        "network_interceptor": 0,
        "has_description": 0,
        "has_element_info": 0,
        "has_action_coords": 0,
    }
    
    print("检查样本质量...\n")
    
    for filename in files[:5]:  # 抽样检查前5个
        meta_path = os.path.join(meta_dir, filename)
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            
            print(f"{filename}:")
            
            # 检查网络拦截日志
            interceptor_logs = meta.get("interceptor_logs", [])
            if interceptor_logs:
                quality_checks["network_interceptor"] += 1
                print(f"  [✓] 网络拦截: {len(interceptor_logs)} 条日志")
                for log in interceptor_logs[:2]:
                    print(f"       - {log.get('type', 'unknown')}: {log.get('url', 'N/A')[:50]}")
            else:
                print(f"  [✗] 网络拦截: 无日志 (可能使用了验证类bug)")
            
            # 检查描述
            desc = meta.get("description", "")
            if desc and len(desc) > 10:
                quality_checks["has_description"] += 1
                print(f"  [✓] 描述: {desc[:60]}...")
            
            # 检查元素信息
            elem_info = meta.get("element_semantic", {})
            if elem_info.get("readable_name"):
                quality_checks["has_element_info"] += 1
                print(f"  [✓] 目标元素: {elem_info.get('readable_name')}")
            
            # 检查点击坐标
            coords = meta.get("action_trace", {}).get("coordinates", [])
            if len(coords) == 2 and coords[0] > 0 and coords[1] > 0:
                quality_checks["has_action_coords"] += 1
                print(f"  [✓] 点击坐标: ({coords[0]}, {coords[1]})")
            
            print()
        except Exception as e:
            print(f"  [!] 错误: {e}\n")
    
    print("="*70)
    print("质量指标:")
    for check, count in quality_checks.items():
        pct = 100 * count / min(5, len(files)) if len(files) > 0 else 0
        print(f"  • {check}: {count}/{min(5, len(files))} ({pct:.0f}%)")


def main():
    print("\n" + "="*70)
    print("🔍 样本质量检查工具")
    print("="*70)
    
    # 执行所有检查
    images_ok = check_images()
    metadata_ok = check_metadata()
    check_bug_injection()
    
    # 总结
    print("\n" + "="*70)
    print("📋 检查总结")
    print("="*70)
    
    if images_ok and metadata_ok:
        print("\n✅ 所有检查通过！样本可用于进一步处理。\n")
    else:
        print("\n⚠️  存在问题，请检查上面的输出。\n")
    
    print("建议:")
    print("  1. 查看 dataset_injected/images/interaction/ 中的 *_action.png")
    print("  2. 检查右上角红标是否清晰可见")
    print("  3. 检查 dataset_injected/raw_metadata/ 中的 JSON 元数据")
    print("  4. 验证 injection_verified 字段是否为 true\n")


if __name__ == "__main__":
    main()
