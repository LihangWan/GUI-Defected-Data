"""
数据质量深度分析工具
"""
import json
from pathlib import Path
from collections import defaultdict, Counter

meta_dir = Path("dataset_injected/raw_metadata")
all_meta = [json.loads(f.read_text(encoding='utf-8')) for f in meta_dir.glob("int_*.json")]

print(f"\n{'='*70}")
print(f"📊 数据质量深度分析报告")
print(f"{'='*70}")
print(f"总样本数: {len(all_meta)}")

# 1. 综合验证统计
verified = sum(m.get("injection_verified", False) for m in all_meta)
visual_verified = sum(m.get("visual_verified", False) for m in all_meta)
has_logs = sum(m.get("has_network_logs", False) for m in all_meta)

print(f"\n【综合验证率】")
print(f"  injection_verified: {verified}/{len(all_meta)} ({verified/len(all_meta)*100:.1f}%)")
print(f"  visual_verified:    {visual_verified}/{len(all_meta)} ({visual_verified/len(all_meta)*100:.1f}%)")
print(f"  has_network_logs:   {has_logs}/{len(all_meta)} ({has_logs/len(all_meta)*100:.1f}%)")

quality_score = (verified/len(all_meta)*0.6 + visual_verified/len(all_meta)*0.4)*100
print(f"\n  🎯 质量得分: {quality_score:.1f}/100")
if quality_score >= 80:
    print(f"     评级: ⭐⭐⭐ 卓越")
elif quality_score >= 60:
    print(f"     评级: ⭐⭐ 良好")
elif quality_score >= 40:
    print(f"     评级: ⭐ 及格")
else:
    print(f"     评级: ⚠️ 需改进")

# 2. 按Bug类型统计
bug_stats = defaultdict(lambda: {"total": 0, "verified": 0, "visual_verified": 0, "has_logs": 0})

for m in all_meta:
    bt = m["bug_type"]
    bug_stats[bt]["total"] += 1
    if m.get("injection_verified"):
        bug_stats[bt]["verified"] += 1
    if m.get("visual_verified"):
        bug_stats[bt]["visual_verified"] += 1
    if m.get("has_network_logs"):
        bug_stats[bt]["has_logs"] += 1

print(f"\n{'='*70}")
print(f"【按Bug类型分析】")
print(f"{'='*70}")
for bug, stats in sorted(bug_stats.items(), key=lambda x: x[1]["verified"]/x[1]["total"], reverse=True):
    v_rate = stats["verified"] / stats["total"] * 100
    vis_rate = stats["visual_verified"] / stats["total"] * 100
    log_rate = stats["has_logs"] / stats["total"] * 100
    
    rating = "⭐⭐⭐" if v_rate >= 80 else "⭐⭐" if v_rate >= 60 else "⭐" if v_rate >= 40 else "⚠️"
    
    print(f"\n{bug} {rating}")
    print(f"  总数: {stats['total']}")
    print(f"  验证率:      {v_rate:.1f}%  {'✓' if v_rate >= 70 else '✗'}")
    print(f"  视觉验证率:  {vis_rate:.1f}%  {'✓' if vis_rate >= 60 else '✗'}")
    print(f"  网络日志率:  {log_rate:.1f}%  {'✓' if log_rate >= 80 else '✗'}")

# 3. 高质量样本分析
high_quality = [m for m in all_meta if m.get("injection_verified") and m.get("visual_verified")]
print(f"\n{'='*70}")
print(f"【高质量样本特征】(verified=True + visual_verified=True)")
print(f"{'='*70}")
print(f"数量: {len(high_quality)}/{len(all_meta)} ({len(high_quality)/len(all_meta)*100:.1f}%)")

if high_quality:
    print(f"\n最常见元素类型:")
    elem_types = [m["element_semantic"]["tag"] for m in high_quality]
    for tag, count in Counter(elem_types).most_common(5):
        print(f"  • {tag}: {count}")
    
    print(f"\n最常见Bug类型:")
    bug_types = [m["bug_type"] for m in high_quality]
    for bug, count in Counter(bug_types).most_common():
        print(f"  • {bug}: {count}")
    
    print(f"\n平均视觉信号:")
    avg_similarity = sum(m.get("visual_signals", {}).get("similarity", 0) for m in high_quality) / len(high_quality)
    has_spinner = sum(m.get("visual_signals", {}).get("has_spinner", False) for m in high_quality)
    has_error = sum(m.get("visual_signals", {}).get("has_error_ele", False) for m in high_quality)
    print(f"  相似度: {avg_similarity:.3f}")
    print(f"  有spinner: {has_spinner}/{len(high_quality)}")
    print(f"  有error元素: {has_error}/{len(high_quality)}")

# 4. 低质量样本分析
low_quality = [m for m in all_meta if not m.get("injection_verified")]
print(f"\n{'='*70}")
print(f"【低质量样本诊断】(verified=False)")
print(f"{'='*70}")
print(f"数量: {len(low_quality)}/{len(all_meta)} ({len(low_quality)/len(all_meta)*100:.1f}%)")

if low_quality:
    print(f"\n常见失败元素类型:")
    elem_types = [m["element_semantic"]["tag"] for m in low_quality]
    for tag, count in Counter(elem_types).most_common(5):
        print(f"  • {tag}: {count}")
    
    print(f"\n常见失败Bug类型:")
    bug_types = [m["bug_type"] for m in low_quality]
    for bug, count in Counter(bug_types).most_common():
        print(f"  • {bug}: {count}")
    
    # 无网络日志的比例
    no_logs = sum(1 for m in low_quality if not m.get("has_network_logs"))
    print(f"\n无网络日志: {no_logs}/{len(low_quality)} ({no_logs/len(low_quality)*100:.1f}%)")
    
    print(f"\n典型失败案例（前3个）:")
    for i, m in enumerate(low_quality[:3], 1):
        print(f"\n  {i}. {m['id']}")
        print(f"     Bug: {m['bug_type']}")
        print(f"     元素: {m['element_semantic']['tag']} - {m['element_semantic']['readable_name'][:40]}")
        print(f"     网络日志: {len(m.get('interceptor_logs', []))}")
        signals = m.get('visual_signals', {})
        print(f"     视觉信号: similarity={signals.get('similarity', 0):.3f}, "
              f"spinner={signals.get('has_spinner', False)}, "
              f"error={signals.get('has_error_ele', False)}")

# 5. 建议
print(f"\n{'='*70}")
print(f"【优化建议】")
print(f"{'='*70}")

issues = []
if verified/len(all_meta) < 0.7:
    issues.append("验证率偏低")
if visual_verified/len(all_meta) < 0.6:
    issues.append("视觉验证率偏低")
if has_logs/len(all_meta) < 0.8:
    issues.append("网络拦截成功率低")

if not issues:
    print("✅ 数据质量优秀，无明显问题！")
else:
    print(f"⚠️ 发现 {len(issues)} 个问题:\n")
    
    if "验证率偏低" in issues:
        print("1. 【验证率偏低】")
        print("   → 优化候选元素选择，过滤无效元素（参考 quality_check_guide.md 策略2）")
        print("   → 提前注入JS拦截器（策略1）\n")
    
    if "视觉验证率偏低" in issues:
        print("2. 【视觉验证率偏低】")
        print("   → 放宽启发式规则判定条件（策略3）")
        print("   → 增加异步UI捕捉等待时间（策略4）\n")
    
    if "网络拦截成功率低" in issues:
        print("3. 【网络拦截成功率低】")
        # 分析失败原因
        no_log_samples = [m for m in all_meta if not m.get("has_network_logs")]
        if no_log_samples:
            failed_bugs = Counter([m["bug_type"] for m in no_log_samples])
            print(f"   无日志Bug类型分布: {dict(failed_bugs)}")
            print("   → 某些Bug类型的元素可能不触发网络请求")
            print("   → 考虑为这些Bug类型单独优化元素选择逻辑\n")

print(f"\n💡 下一步行动:")
print(f"1. 查看 quality_check_guide.md 获取详细优化方案")
print(f"2. 运行 visual_review.py 生成可视化审查图像")
print(f"3. 实施一项优化后，重新生成10-20个样本对比效果")
print(f"{'='*70}\n")
