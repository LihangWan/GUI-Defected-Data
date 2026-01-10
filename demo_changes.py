#!/usr/bin/env python3
"""
修改对比演示脚本
展示修改前后的代码差异和效果
"""

import json
from datetime import datetime


def print_section(title):
    """打印章节标题"""
    print("\n" + "="*70)
    print(f"📋 {title}")
    print("="*70 + "\n")


def show_red_tag_fix():
    """展示红标修复"""
    print_section("修复1: 红标显示（capture.py）")
    
    print("❌ 修改前 (有问题):")
    print("""
    # Simple top-right box
    box_w, box_h = 300, 40
    pad_x, pad_y = 20, 15
    bx = img.width - box_w - pad_x
    by = pad_y
    
    # Black background with transparency
    draw.rectangle([bx, by, bx+box_w, by+box_h], fill=(0, 0, 0, 200))
    
    # Red tag (尺寸太小，颜色不对)
    tag_w = 120
    tag_h = 24
    tx = bx + 10
    ty = by + 8
    draw.rectangle([tx, ty, tx+tag_w, ty+tag_h], fill=(255, 107, 107, 255))
    """)
    
    print("\n问题:")
    print("  • 红标尺寸只有 120x24，太小了")
    print("  • 红色值 (255, 107, 107) 太浅，不够突出")
    print("  • 位置依赖于黑色背景，背景可能被其他内容覆盖")
    print("  • 没有边框，对比度低")
    
    print("\n" + "-"*70)
    print("\n✅ 修改后 (已修复):")
    print("""
    # Red tag dimensions and positioning
    tag_w = 140
    tag_h = 32
    pad_x, pad_y = 16, 12
    tx = img.width - tag_w - pad_x  # Right-aligned
    ty = pad_y                       # Top position
    
    # Draw red background rectangle with border
    draw.rectangle([tx, ty, tx+tag_w, ty+tag_h], 
                  fill=(239, 68, 68, 240),      # 更亮的红色
                  outline=(220, 53, 53, 255))   # 边框
    
    # Draw text in the red tag
    label_text = str(label)[:16]
    draw.text((tx + 8, ty + 7), label_text, fill=(255, 255, 255, 255))
    """)
    
    print("\n改进:")
    print("  ✓ 尺寸增加到 140x32，更容易看清")
    print("  ✓ 使用更亮的红 (239, 68, 68) 和边框 (220, 53, 53)")
    print("  ✓ 红标独立显示，不依赖黑色背景")
    print("  ✓ 添加了边框，提高对比度和可见性")
    print("  ✓ 直接在红标内显示文字，布局更清晰")


def show_injection_validation_fix():
    """展示注入验证修复"""
    print_section("修复2: 注入验证和日志（injectors.py）")
    
    print("❌ 修改前 (没有反馈):")
    print("""
    def inject_operation_no_response(self, element):
        if self.use_js_interceptor:
            self.js_interceptor.inject_fetch_interceptor()
            self.js_interceptor.intercept_request_timeout(r'.*')
            # 没有任何返回值检查，无法确认是否成功
        return "Operation_No_Response", "..."
    """)
    
    print("\n问题:")
    print("  • intercept_request_timeout() 的返回值被忽略")
    print("  • 用户无法看到是否真的成功注入了")
    print("  • 日志输出中看不到 [✓] 或 [✗]")
    print("  • 无法追踪哪个样本的注入失败了")
    
    print("\n" + "-"*70)
    print("\n✅ 修改后 (有验证):")
    print("""
    def inject_operation_no_response(self, element):
        injection_success = False
        if self.use_js_interceptor:
            self.js_interceptor.inject_fetch_interceptor()
            injection_success = self.js_interceptor.intercept_request_timeout(r'.*')
            # ↑ 捕获返回值，判断是否成功
            try:
                self.driver.execute_script(...)
            except Exception:
                pass
        status = "✓ Injected" if injection_success else "✗ Failed"
        print(f"  [Inject] Operation_No_Response: {status}")  # 输出状态
        return "Operation_No_Response", "..."
    """)
    
    print("\n改进:")
    print("  ✓ 捕获注入是否成功（True/False）")
    print("  ✓ 实时输出 [✓ Injected] 或 [✗ Failed]")
    print("  ✓ 所有6种bug类型都有验证")
    print("  ✓ 用户可以清楚地看到哪个注入成功了")
    
    print("\n" + "-"*70)
    print("\nlog输出对比:")
    print("\n❌ 修改前:")
    print("""
    [*] Loading: http://localhost:3000
    [+] Interaction bug injected: int_abc123 | Timeout_Hang
    """)
    
    print("\n✅ 修改后:")
    print("""
    [*] Loading: http://localhost:3000
    🔍 PAGE FEATURE SUMMARY
    ✅ Allowed Bugs: Navigation_Error, Timeout_Hang, ...
    
      [Action] Overlay visualized: Timeout_Hang
      [Execute] Bug type: timeout → Timeout_Hang
      [Inject] Timeout_Hang: ✓ Injected           ← 验证成功！
      [Overlay] Setting overlay: Timeout_Hang
      [Click] Successfully clicked element
    ✓ [Stored] int_abc123 | Timeout_Hang | Logs: 2  ← 有拦截日志
    """)


def show_metadata_enhancement():
    """展示元数据增强"""
    print_section("修复3: 元数据增强（injectors.py）")
    
    print("❌ 修改前 (元数据不完整):")
    old_meta = {
        "id": "int_abc123",
        "bug_type": "Timeout_Hang",
        "url": "http://localhost:3000",
        # 没有 injection_verified 字段
    }
    print(json.dumps(old_meta, ensure_ascii=False, indent=2))
    
    print("\n问题:")
    print("  • 无法判断注入是否真的成功了")
    print("  • 需要手动检查 interceptor_logs 才能确认")
    print("  • 无法快速统计验证成功率")
    
    print("\n" + "-"*70)
    print("\n✅ 修改后 (元数据完整):")
    new_meta = {
        "id": "int_abc123",
        "bug_type": "Timeout_Hang",
        "url": "http://localhost:3000",
        "injection_verified": True,  # ← 新增字段
        "interceptor_logs": [
            {"type": "timeout", "url": "http://localhost:3000/api/data"}
        ],
        "timestamp": "2024-01-09 10:30:45.123456",
    }
    print(json.dumps(new_meta, ensure_ascii=False, indent=2))
    
    print("\n改进:")
    print("  ✓ 新增 injection_verified 字段")
    print("  ✓ 自动基于 interceptor_logs 或 bug_type 判断")
    print("  ✓ 快速查看样本质量: grep 'injection_verified' *.json")
    print("  ✓ 可以按验证状态筛选样本")


def show_new_tools():
    """展示新增工具"""
    print_section("修复4: 新增工具脚本")
    
    print("🔧 quick_sample_generator.py")
    print("""
    用途: 快速生成小批量样本用于检查
    
    功能:
    • 清理旧数据并备份
    • 以调试模式运行（更快）
    • 生成 6 个样本
    • 自动分析结果
    
    使用: python quick_sample_generator.py
    时间: 约 5-10 分钟
    """)
    
    print("\n" + "-"*70)
    print("\n🔍 check_samples.py")
    print("""
    用途: 验证生成样本的质量
    
    检查项:
    1. 图片完整性 - 检查start/action/end三张图
    2. 红标检测 - 检查action图右上角是否有红色像素
    3. 元数据检查 - 验证所有必需字段
    4. 验证状态 - 检查injection_verified是否为true
    5. 质量指标 - 检查日志、坐标、元素信息等
    
    使用: python check_samples.py
    输出: 详细的质量报告
    """)


def show_example_output():
    """展示示例输出"""
    print_section("预期输出效果")
    
    print("运行 quick_sample_generator.py 后的日志示例:")
    print("""
🚀 快速样本生成器 - Bug注入效果检查
======================================

[*] 启动注入引擎（调试模式）

[*] 开始生成样本...
    配置:
    • 每个页面: 6 个样本
    • 启用网络拦截: 是
    • 启用可视化: 是
    • 调试模式: 是

[*] Loading: http://localhost:3000
🔍 PAGE FEATURE SUMMARY
====================================
Page Type: INTERACTIVE
Forms: 2 | Inputs: 5 | Buttons: 8
✅ Allowed Bugs: Navigation_Error, Timeout_Hang, Operation_No_Response, ...
⚖️  Bug Weights: {'Navigation_Error': 1.0, 'Timeout_Hang': 1.5, ...}
====================================

  [Action] Overlay visualized: Timeout_Hang
  [Execute] Bug type: timeout → Timeout_Hang
  [Inject] Timeout_Hang: ✓ Injected
  [Overlay] Setting overlay: Timeout_Hang
  [Click] Successfully clicked element
  [Final] Writing metadata with bug=Timeout_Hang
✓ [Stored] int_xyz789 | Timeout_Hang | Logs: 2

  [Action] Overlay visualized: Validation_Error
  [Execute] Bug type: validation → Validation_Error
  [Inject] Validation_Error: ✓ Injected (invalid data into input)
  [Overlay] Setting overlay: Validation_Error
  [Click] Successfully clicked element
  [Final] Writing metadata with bug=Validation_Error
✓ [Stored] int_abc456 | Validation_Error | Logs: 0

  ...（4个更多样本）...

📊 生成样本统计 (共 6 个)
====================================
  int_xyz789_start.png
    ├─ Bug类型: Timeout_Hang
    ├─ 状态: ✓ 已验证
    ├─ URL: http://localhost:3000
    ├─ 目标元素: "Login"
    └─ 网络日志: 2 条

  int_abc456_start.png
    ├─ Bug类型: Validation_Error
    ├─ 状态: ✓ 已验证
    ├─ URL: http://localhost:3000
    ├─ 目标元素: "Email"
    └─ 网络日志: 0 条
    
  ... (4个更多) ...

📈 Bug类型分布:
  • Timeout_Hang: 2
  • Validation_Error: 2
  • Navigation_Error: 1
  • Unexpected_Task_Result: 1

✅ 验证统计:
  • 已验证: 6
  • 未验证: 0
  • 验证率: 100.0%
    """)


def show_verification_checklist():
    """展示验证清单"""
    print_section("验证清单")
    
    print("""
运行完成后，按以下步骤验证修复:

1. ✅ 图片检查
   [ ] 打开 dataset_injected/images/interaction/*.png
   [ ] 检查 *_action.png 图片右上角是否有**清晰的红标**
   [ ] 红标内应该显示bug类型（如 "Timeout_Hang"）
   [ ] 红标颜色应该是亮红色 RGB(239,68,68)

2. ✅ 元数据检查
   [ ] 打开 dataset_injected/raw_metadata/*.json
   [ ] 查找 "injection_verified" 字段，应该是 true
   [ ] 查找 "interceptor_logs"，应该有内容（如果是网络bug）
   [ ] 查找 "bug_type"，应该是有效的类型之一
   [ ] 查找 "element_semantic"，应该包含元素信息

3. ✅ 验证率检查
   [ ] 运行 python check_samples.py
   [ ] 查看 "验证率" 行，应该是 >= 80%
   [ ] 查看 Bug 类型分布，应该覆盖多种类型

4. ✅ 日志确认
   [ ] 在运行日志中看到 [✓ Injected] 或 [✓ Injected (invalid data into input)]
   [ ] 在最终统计中看到 "已验证: X/6"
   [ ] 没有看到太多的 [✗ Failed] 错误

如果以上所有检查都通过，说明修复成功！ 🎉
    """)


def main():
    print("\n" + "="*70)
    print("🔧 Bug注入系统修复 - 对比演示")
    print("="*70)
    
    show_red_tag_fix()
    show_injection_validation_fix()
    show_metadata_enhancement()
    show_new_tools()
    show_example_output()
    show_verification_checklist()
    
    print("\n" + "="*70)
    print("✅ 演示完成")
    print("="*70)
    print("\n后续步骤:")
    print("  1. python quick_sample_generator.py  # 生成样本")
    print("  2. python check_samples.py            # 检查质量")
    print("  3. 查看 dataset_injected/ 目录        # 查看结果\n")


if __name__ == "__main__":
    main()
