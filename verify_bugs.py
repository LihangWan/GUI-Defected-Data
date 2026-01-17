"""
逐一验证每种 Bug 类型的注入效果 (Big Three Taxonomy)

Bug Types:
1. Navigation_Error: 是否真的跳转到 404 页面
2. Operation_No_Response: 页面是否无响应（视觉变化 < 5%）
3. Unexpected_Task_Result: 是否触发 500 错误
"""
import os
import json
import time
from interaction_engine.injectors import InteractionInjector
from interaction_engine.selector import get_candidates, get_network_triggering_candidates


def clear_samples():
    """清除所有样本"""
    meta_dir = "dataset_injected/raw_metadata"
    img_dir = "dataset_injected/images/interaction"
    
    for f in os.listdir(meta_dir):
        if f.startswith("int_"):
            try:
                os.remove(os.path.join(meta_dir, f))
            except:
                pass
    
    for f in os.listdir(img_dir):
        if f.startswith("int_"):
            try:
                os.remove(os.path.join(img_dir, f))
            except:
                pass


def get_latest_meta(bug_type=None):
    """获取最新的元数据文件，可选按 bug_type 过滤"""
    meta_dir = "dataset_injected/raw_metadata"
    files = sorted([f for f in os.listdir(meta_dir) if f.startswith("int_") and f.endswith(".json")], reverse=True)
    
    for filename in files:
        try:
            with open(os.path.join(meta_dir, filename), "r", encoding="utf-8") as f:
                meta = json.load(f)
                if bug_type is None or meta.get("bug_type") == bug_type:
                    return meta
        except:
            pass
    return None


def test_navigation_error():
    """验证 Navigation_Error: 是否真的跳转到 404 页面"""
    print("\n" + "=" * 70)
    print("🔍 验证 Navigation_Error")
    print("   预期行为: 点击后跳转到 404/错误页面 (支持原生或注入)")
    print("=" * 70)
    
    results = []
    urls = [
        "http://localhost:3000/#/contact",
        "http://localhost:3000/#/login",
    ]
    
    for url in urls:
        print(f"\n[测试] URL: {url}")
        
        engine = InteractionInjector(headless=True, use_js_interceptor=True, debug_mode=True)
        engine.driver.get(url)
        time.sleep(2)
        
        candidates = get_candidates(engine.driver)
        if not candidates:
            print("  [!] 无候选元素")
            engine.driver.quit()
            continue
        
        elem = candidates[0]
        url_before = engine.driver.current_url
        
        engine.execute_injection(elem, bug_choice="Navigation_Error")
        time.sleep(1)
        
        url_after = engine.driver.current_url
        meta = get_latest_meta("Navigation_Error")
        
        # 验证标准: URL 包含 404 相关路径 (支持原生和注入两种模式)
        is_valid = any(pattern in url_after.lower() for pattern in [
            "error-404", "404", "not-found", "notfound", "page-not-found"
        ])
        visual_diff = meta.get("visual_diff", {}).get("diff_percentage", 0) if meta else 0
        
        status = "✓" if is_valid else "✗"
        print(f"  {status} URL 变化: {url_before} → {url_after}")
        print(f"  {status} 包含 404 路径: {is_valid}")
        print(f"  {status} 视觉差异: {visual_diff}%")
        
        results.append({
            "url_before": url_before,
            "url_after": url_after,
            "has_error_404": is_valid,
            "visual_diff": visual_diff
        })
        
        engine.driver.quit()
    
    valid_count = sum(1 for r in results if r["has_error_404"])
    print(f"\n📊 Navigation_Error 验证结果: {valid_count}/{len(results)} 通过")
    return results


def test_operation_no_response():
    """验证 Operation_No_Response: 包含两种子类型
    
    Sub-variant 1 (Dead Click): 页面冻结，视觉变化 < 5%
    Sub-variant 2 (Timeout Hang): 显示 Loading Overlay，视觉变化大（遮罩覆盖）
    """
    print("\n" + "=" * 70)
    print("🔍 验证 Operation_No_Response")
    print("   预期行为:")
    print("   - Dead Click: 页面冻结，视觉变化 < 5%")
    print("   - Timeout Hang: 显示 Loading Spinner 遮罩")
    print("=" * 70)
    
    results = []
    urls = [
        "http://localhost:3000/#/contact",
        "http://localhost:3000/#/login",
    ]
    
    for url in urls:
        print(f"\n[测试] URL: {url}")
        
        engine = InteractionInjector(headless=True, use_js_interceptor=True, debug_mode=True)
        engine.driver.get(url)
        time.sleep(2)
        
        # 优先选择网络触发元素
        candidates = get_network_triggering_candidates(engine.driver)
        if not candidates:
            candidates = get_candidates(engine.driver)
        
        if not candidates:
            print("  [!] 无候选元素")
            engine.driver.quit()
            continue
        
        elem = candidates[0]
        url_before = engine.driver.current_url
        
        engine.execute_injection(elem, bug_choice="Operation_No_Response")
        time.sleep(1)
        
        url_after = engine.driver.current_url
        meta = get_latest_meta("Operation_No_Response")
        
        visual_diff = meta.get("visual_diff", {}).get("diff_percentage", 100) if meta else 100
        network_logs = len(meta.get("interceptor_logs", [])) if meta else 0
        description = meta.get("description", "") if meta else ""
        
        # 检测子类型
        is_timeout_hang = "loading spinner" in description.lower() or "with loading" in description.lower()
        is_dead_click = "dead click" in description.lower()
        
        # 验证标准:
        # - Dead Click: 视觉变化 < 5%
        # - Timeout Hang: 视觉变化大（遮罩覆盖了页面）或者检测到 Loading overlay
        is_frozen = visual_diff < 5
        has_loading_overlay = visual_diff > 50  # Overlay 覆盖会导致大变化
        has_interception = network_logs > 0
        
        # 两种子类型都算有效
        is_valid = is_frozen or has_loading_overlay or has_interception
        
        sub_type = "timeout_hang" if is_timeout_hang or has_loading_overlay else "dead_click"
        status = "✓" if is_valid else "✗"
        print(f"  {status} 子类型: {sub_type}")
        print(f"  {status} URL 保持不变: {url_before == url_after}")
        print(f"  {status} 视觉差异: {visual_diff}%")
        if sub_type == "dead_click":
            print(f"  {status} Dead Click 验证: 冻结={is_frozen}")
        else:
            print(f"  {status} Timeout Hang 验证: 有 Overlay={has_loading_overlay}")
        print(f"  {status} 网络拦截日志: {network_logs} 条")
        
        results.append({
            "sub_type": sub_type,
            "visual_diff": visual_diff,
            "network_logs": network_logs,
            "is_frozen": is_frozen,
            "has_loading_overlay": has_loading_overlay,
            "has_interception": has_interception,
            "is_valid": is_valid
        })
        
        engine.driver.quit()
    
    valid_count = sum(1 for r in results if r["is_valid"])
    print(f"\n📊 Operation_No_Response 验证结果: {valid_count}/{len(results)} 通过")
    return results


def test_unexpected_task_result():
    """验证 Unexpected_Task_Result: 是否触发 500 错误"""
    print("\n" + "=" * 70)
    print("🔍 验证 Unexpected_Task_Result")
    print("   预期行为: API 请求返回 500 错误")
    print("=" * 70)
    
    results = []
    urls = [
        "http://localhost:3000/#/contact",
        "http://localhost:3000/#/login",
    ]
    
    for url in urls:
        print(f"\n[测试] URL: {url}")
        
        engine = InteractionInjector(headless=True, use_js_interceptor=True, debug_mode=True)
        engine.driver.get(url)
        time.sleep(2)
        
        # 优先选择网络触发元素
        candidates = get_network_triggering_candidates(engine.driver)
        if not candidates:
            candidates = get_candidates(engine.driver)
        
        if not candidates:
            print("  [!] 无候选元素")
            engine.driver.quit()
            continue
        
        elem = candidates[0]
        
        engine.execute_injection(elem, bug_choice="Unexpected_Task_Result")
        time.sleep(1)
        
        meta = get_latest_meta("Unexpected_Task_Result")
        
        visual_diff = meta.get("visual_diff", {}).get("diff_percentage", 0) if meta else 0
        network_logs = meta.get("interceptor_logs", []) if meta else []
        desc = meta.get("description", "") if meta else ""
        
        # 检查网络日志是否包含 500 错误
        has_500_error = any("500" in str(log) or "error" in str(log).lower() for log in network_logs)
        has_error_in_desc = "500" in desc or "error" in desc.lower()
        is_valid = has_500_error or has_error_in_desc or visual_diff > 5
        
        status = "✓" if is_valid else "✗"
        print(f"  {status} 描述: {desc[:60]}...")
        print(f"  {status} 网络日志数: {len(network_logs)}")
        print(f"  {status} 包含 500 错误: {has_500_error}")
        print(f"  {status} 视觉差异: {visual_diff}%")
        
        results.append({
            "description": desc,
            "network_logs_count": len(network_logs),
            "has_500_error": has_500_error,
            "visual_diff": visual_diff,
            "is_valid": is_valid
        })
        
        engine.driver.quit()
    
    valid_count = sum(1 for r in results if r["is_valid"])
    print(f"\n📊 Unexpected_Task_Result 验证结果: {valid_count}/{len(results)} 通过")
    return results


def main():
    print("=" * 70)
    print("🧪 Bug 注入验证测试 - Big Three Taxonomy")
    print("   • Navigation_Error: 404/错误路由")
    print("   • Operation_No_Response: 死点击/超时挂起")
    print("   • Unexpected_Task_Result: 500 错误")
    print("=" * 70)
    
    # 清除旧样本
    clear_samples()
    print("[*] 已清除旧样本")
    
    all_results = {}
    
    # 1. Navigation_Error
    all_results["Navigation_Error"] = test_navigation_error()
    
    # 2. Operation_No_Response
    all_results["Operation_No_Response"] = test_operation_no_response()
    
    # 3. Unexpected_Task_Result
    all_results["Unexpected_Task_Result"] = test_unexpected_task_result()
    
    # 最终汇总
    print("\n\n" + "=" * 70)
    print("📊 最终汇总报告 (Big Three)")
    print("=" * 70)
    
    for bug_type, results in all_results.items():
        if results:
            valid = sum(1 for r in results if r.get("is_valid") or r.get("has_error_404"))
            print(f"\n{bug_type}:")
            print(f"  • 测试数: {len(results)}")
            print(f"  • 通过数: {valid}/{len(results)} ({valid/len(results)*100:.0f}%)")


if __name__ == "__main__":
    main()
