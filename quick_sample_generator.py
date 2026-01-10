#!/usr/bin/env python3
"""
快速生成小批量样本用于检查bug注入效果
生成 5-10 个样本，包括所有bug类型
"""

import os
import shutil
import json
from datetime import datetime

from interaction_engine.injectors import InteractionInjector


def clean_old_samples():
    """清理旧的样本数据"""
    dataset_dir = "dataset_injected"
    if os.path.exists(dataset_dir):
        print(f"[*] 清理旧数据: {dataset_dir}")
        # 备份元数据和图片
        backup_dir = f"dataset_injected_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not os.path.exists("backups"):
            os.makedirs("backups")
        backup_path = os.path.join("backups", backup_dir)
        shutil.copytree(dataset_dir, backup_path, dirs_exist_ok=True)
        print(f"    已备份到: {backup_path}")
        
        # 清空目录但保留结构
        for root, dirs, files in os.walk(dataset_dir):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                except:
                    pass


def analyze_results():
    """分析生成的样本"""
    meta_dir = "dataset_injected/raw_metadata"
    if not os.path.exists(meta_dir):
        print("[-] 没有找到元数据目录")
        return
    
    files = [f for f in os.listdir(meta_dir) if f.startswith("int_") and f.endswith(".json")]
    print(f"\n{'='*70}")
    print(f"📊 生成样本统计 (共 {len(files)} 个)")
    print(f"{'='*70}\n")
    
    bug_stats = {}
    verification_stats = {"verified": 0, "unverified": 0}
    
    for filename in sorted(files):
        meta_path = os.path.join(meta_dir, filename)
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            
            bug_type = meta.get("bug_type", "Unknown")
            is_verified = meta.get("injection_verified", False)
            interceptor_logs = meta.get("interceptor_logs", [])
            console_logs = meta.get("console_logs", [])
            
            bug_stats[bug_type] = bug_stats.get(bug_type, 0) + 1
            if is_verified:
                verification_stats["verified"] += 1
            else:
                verification_stats["unverified"] += 1
            
            # 打印样本信息
            status = "✓ 已验证" if is_verified else "? 未验证"
            print(f"  {filename}")
            print(f"    ├─ Bug类型: {bug_type}")
            print(f"    ├─ 状态: {status}")
            print(f"    ├─ URL: {meta.get('url', 'Unknown')}")
            print(f"    ├─ 目标元素: {meta.get('element_semantic', {}).get('readable_name', 'Unknown')}")
            print(f"    ├─ 截图: start, action, end")
            print(f"    ├─ 网络日志: {len(interceptor_logs)} 条")
            print(f"    └─ 控制台日志: {len(console_logs)} 条\n")
        except Exception as e:
            print(f"  [!] 无法读取 {filename}: {e}\n")
    
    print(f"{'='*70}")
    print(f"📈 Bug类型分布:")
    for bug_type, count in sorted(bug_stats.items()):
        print(f"  • {bug_type}: {count}")
    
    print(f"\n✅ 验证统计:")
    print(f"  • 已验证: {verification_stats['verified']}")
    print(f"  • 未验证: {verification_stats['unverified']}")
    print(f"  • 验证率: {100*verification_stats['verified']/len(files):.1f}%")
    print(f"{'='*70}\n")


def main():
    print("\n" + "="*70)
    print("🚀 快速样本生成器 - Bug注入效果检查")
    print("="*70 + "\n")
    
    # 清理旧数据
    clean_old_samples()
    
    # 配置：仅使用本地测试站点，快速生成少量样本
    targets = {
        "test_site": {
            "base": "http://localhost:3000",  # OWASP Juice Shop
            "routes": [
                # 表单密集页面 (优先测试)
                "/#/login",
                "/#/register", 
                "/#/contact",
                "/#/complain",
                "/#/forgot-password",
                # 交互元素多的页面
                "/#/search",
                "/#/basket",
                "/#/chatbot",
                "/#/track-result",
                "/#/recycle",
            ],
            "auth_required": False,
        }
    }
    
    print("[*] 启动注入引擎（调试模式）")
    injector = InteractionInjector(
        headless=True,
        max_wait=10,
        use_js_interceptor=True,
        show_overlay_flag=True,
        debug_mode=True,  # 调试模式：更快的超时和等待
    )
    
    try:
        print("\n[*] 开始生成样本...")
        print("    配置:")
        print("    • 每个页面: 6 个样本")
        print("    • 启用网络拦截: 是")
        print("    • 启用可视化: 是")
        print("    • 调试模式: 是 (加快执行)\n")
        
        injector.run_batch(
            targets,
            samples_per_site=6,
            enable_discovery=False,  # 禁用自动发现，快速测试
            link_limit=0,
            link_samples=0,
        )
    except KeyboardInterrupt:
        print("\n[!] 用户中断")
    except Exception as e:
        print(f"\n[!] 错误: {e}")
    finally:
        injector.close()
    
    # 分析结果
    print("\n[*] 分析结果...")
    analyze_results()
    
    print("\n[✓] 完成！")
    print("\n📁 输出位置:")
    print("  • 图片: dataset_injected/images/interaction/")
    print("  • 元数据: dataset_injected/raw_metadata/")
    print("  • 备份: backups/\n")


if __name__ == "__main__":
    main()
