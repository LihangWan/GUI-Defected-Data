# 🎯 数据质量优化指南

## 📊 当前状态分析（基于测试样本）

### ✅ 已正常工作的功能
- ✓ 元数据包含 `visual_verified`, `visual_signals` 字段
- ✓ 网络拦截日志正常记录
- ✓ 视觉启发式规则已生效
- ✓ 综合验证逻辑工作（visual + network）

### ⚠️ 观察到的问题
**验证率: 30% (3/10)** - 较低，需要优化

**问题分析：**
1. **网络拦截失败率高** - 多个样本显示 `[Inject] xxx: ✗ Failed`
2. **元素未触发网络请求** - 如图片卡片、语言切换按钮等非交互元素
3. **视觉信号不明显** - 有网络日志但 `visual_verified=false`（如 int_4bcb701f）

---

## 🔍 质量检查流程

### 第1步：元数据质量检查

```bash
# 查看所有样本的验证状态
python check_samples.py

# 重点关注指标：
# • injection_verified: 综合验证率（目标 >70%）
# • visual_verified: 视觉验证率（目标 >60%）
# • has_network_logs: 网络日志率（目标 >80%）
```

**关键字段说明：**
- `injection_verified = true`: 可用于LLM微调的高质量样本
- `visual_verified = true`: 视觉上可明确看到Bug效果
- `visual_signals`: 提供可解释性（为什么判定为可见/不可见）

---

### 第2步：视觉质量审查

```bash
# 生成review图像（带diff热力图）
python visual_review.py

# 打开 dataset_injected/images/interaction/review/ 文件夹
# 人工检查前10-20个样本的start/action/end图像
```

**审查要点：**
1. ✅ **Start图**: 页面是否完整加载？元素是否可见？
2. ✅ **Action图**: 红色标签是否标注在正确位置？
3. ✅ **End图**: 
   - Navigation_Error → 是否出现404/错误页面？
   - Timeout_Hang → 是否有loading spinner？
   - Validation_Error → 是否有红色validation提示？
   - Operation_No_Response → 页面是否几乎无变化（高相似度）？
   - Unexpected_Task_Result → 是否出现错误提示？
4. ✅ **Diff图**: 差异区域是否合理？

**常见问题识别：**
- ❌ End截图和Start完全相同 → 元素未触发任何动作
- ❌ End截图是空白/加载中 → 等待时间不足
- ❌ 红色标签位置不对 → 元素坐标计算错误

---

### 第3步：统计分析与诊断

创建自定义检查脚本：

```python
# analyze_quality.py
import json
from pathlib import Path

meta_dir = Path("dataset_injected/raw_metadata")
all_meta = [json.loads(f.read_text(encoding='utf-8')) for f in meta_dir.glob("int_*.json")]

# 1. 按Bug类型统计验证率
from collections import defaultdict
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

print("\n=== Bug类型验证率分析 ===")
for bug, stats in sorted(bug_stats.items()):
    v_rate = stats["verified"] / stats["total"] * 100
    vis_rate = stats["visual_verified"] / stats["total"] * 100
    log_rate = stats["has_logs"] / stats["total"] * 100
    print(f"\n{bug}:")
    print(f"  总数: {stats['total']}")
    print(f"  验证率: {v_rate:.1f}%")
    print(f"  视觉验证率: {vis_rate:.1f}%")
    print(f"  网络日志率: {log_rate:.1f}%")

# 2. 识别高质量样本特征
high_quality = [m for m in all_meta if m.get("injection_verified") and m.get("visual_verified")]
print(f"\n=== 高质量样本 (verified + visual) ===")
print(f"数量: {len(high_quality)}/{len(all_meta)} ({len(high_quality)/len(all_meta)*100:.1f}%)")
if high_quality:
    print("\n常见元素类型:")
    elem_types = [m["element_semantic"]["tag"] for m in high_quality]
    from collections import Counter
    print(Counter(elem_types).most_common(5))

# 3. 识别低质量样本特征
low_quality = [m for m in all_meta if not m.get("injection_verified")]
print(f"\n=== 低质量样本分析 ===")
print(f"数量: {len(low_quality)}/{len(all_meta)}")
if low_quality:
    print("\n常见失败原因:")
    for m in low_quality[:3]:
        print(f"  • {m['id']}: {m['bug_type']}")
        print(f"    元素: {m['element_semantic']['tag']} - {m['element_semantic']['readable_name'][:40]}")
        print(f"    网络日志: {len(m.get('interceptor_logs', []))}")
        print(f"    视觉信号: {m.get('visual_signals', {})}")
```

---

## 🚀 优化策略

### 策略1: 提高网络拦截成功率

**问题根因：** JS拦截器注入失败或时机不对

**解决方案：**
```python
# 在 interaction_engine/injectors.py 的 _wait_page_ready 中
# 确保拦截器更早注入
def _wait_page_ready(self):
    try:
        WebDriverWait(self.driver, self.max_wait).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        # 提前注入拦截器（在任何元素交互前）
        if self.use_js_interceptor:
            self.js_interceptor.inject_fetch_interceptor()
    except Exception:
        pass
    time.sleep(1 if self.debug_mode else 5)
```

### 策略2: 优化候选元素选择

**问题根因：** 选中的元素不触发网络请求（如纯展示元素）

**优化方向：**
1. **提高选择器权重** - 在 `selector.py` 中提高表单按钮、提交按钮权重
2. **过滤无效元素** - 排除纯图片、纯文本展示元素
3. **验证元素可交互性** - 检查 `is_displayed()` 和 `is_enabled()`

```python
# 在 selector.py 的 get_candidates 中添加过滤
def get_candidates(driver, prioritize_network=True):
    # ... existing code ...
    
    # 过滤掉纯展示元素
    candidates = [el for el in candidates if should_keep(el)]
    
def should_keep(element):
    """过滤掉不太可能触发网络的元素"""
    tag = element.tag_name.lower()
    # 排除纯图片
    if tag == "img":
        return False
    # 排除纯文本span（无role/onclick）
    if tag == "span":
        if not element.get_attribute("role") and not element.get_attribute("onclick"):
            return False
    return True
```

### 策略3: 调整视觉验证启发式规则

**当前问题：** 样本 `int_4bcb701f` 有网络日志但 `visual_verified=false`
- similarity: 0.6104（变化明显）
- has_network_logs: true
- 但所有DOM信号为false

**优化方案：** 放宽 `Operation_No_Response` 的判定条件

```python
# 在 _detect_visual_evidence 中
elif bug_type == "Operation_No_Response":
    # 旧规则：相似度>0.985才算
    # visual_ok = similarity > 0.985 and not signals["has_error_ele"]
    
    # 新规则：页面有变化但没有明确错误提示也算
    visual_ok = (
        (similarity > 0.90) or  # 页面几乎不变
        (has_logs and not signals["has_error_ele"])  # 有请求但无错误元素
    )
```

### 策略4: 增加等待时间捕捉异步效果

**问题：** 某些异步UI变化（如toast提示）可能在截图前消失

**解决：**
```python
# 在 execute_injection 中，click后增加分阶段截图
time.sleep(0.5 if self.debug_mode else 2)
after_dom = self._dom_snapshot()

# 对于网络类bug，多等一会捕捉spinner/error
if bug_type in ["Timeout_Hang", "Unexpected_Task_Result"]:
    time.sleep(1)  # 额外等待异步UI
```

---

## 📈 质量目标

### 最低可用标准
- ✓ 验证率 ≥ 50%
- ✓ 所有样本有start/action/end三张图
- ✓ 元数据完整（无缺失字段）

### 优质数据标准
- ✓ 验证率 ≥ 70%
- ✓ 视觉验证率 ≥ 60%
- ✓ 每种Bug类型至少10个高质量样本
- ✓ 视觉review中人工确认 >90% 正确

### 卓越数据标准
- ✓ 验证率 ≥ 85%
- ✓ 视觉验证率 ≥ 75%
- ✓ Bug类型分布均衡（差异 <20%）
- ✓ 包含多样化页面类型和元素

---

## 🛠️ 实用工具脚本

### 快速质量得分
```bash
# 一键计算质量得分
python -c "
import json
from pathlib import Path
meta = [json.loads(f.read_text(encoding='utf-8')) for f in Path('dataset_injected/raw_metadata').glob('int_*.json')]
verified = sum(m.get('injection_verified', False) for m in meta)
visual = sum(m.get('visual_verified', False) for m in meta)
print(f'Quality Score: {(verified/len(meta)*0.6 + visual/len(meta)*0.4)*100:.1f}/100')
print(f'  Verified: {verified}/{len(meta)} ({verified/len(meta)*100:.1f}%)')
print(f'  Visual: {visual}/{len(meta)} ({visual/len(meta)*100:.1f}%)')
"
```

### 导出低质量样本供调试
```python
# export_low_quality.py
import json
from pathlib import Path

meta_dir = Path("dataset_injected/raw_metadata")
low = [
    m for m in [json.loads(f.read_text(encoding='utf-8')) for f in meta_dir.glob("int_*.json")]
    if not m.get("injection_verified")
]

with open("low_quality_samples.json", "w", encoding="utf-8") as f:
    json.dump(low, f, ensure_ascii=False, indent=2)

print(f"Exported {len(low)} low-quality samples for debugging")
```

---

## 🎓 最佳实践总结

1. **迭代优化** - 每次生成10-20个样本→审查→调整→重新生成
2. **A/B对比** - 修改启发式规则后，对比前后验证率变化
3. **记录问题样本** - 保存典型失败case，作为优化依据
4. **平衡质量与数量** - 先小批量优化到70%验证率，再批量生成
5. **人工校准** - 每100个样本人工抽查10个，确保自动验证准确

---

## 下一步建议

1. ✅ **立即执行**：运行上面的 `analyze_quality.py` 脚本，获取详细统计
2. 🔧 **优先优化**：实施"策略2"过滤无效元素（投入小，收益大）
3. 📊 **持续监控**：每生成50个样本跑一次 `check_samples.py`
4. 🎯 **目标里程碑**：
   - Week 1: 验证率达到 60%
   - Week 2: 验证率达到 75%，视觉验证率 60%+
   - Week 3: 每种Bug类型 ≥20 个高质量样本

**质量优于数量！** 50个高质量样本 > 200个低质量样本
