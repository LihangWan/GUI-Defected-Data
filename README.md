# UI Bug 视觉缺陷数据集自动生成系统

> 一个基于 Selenium + MLLM 的自动化 UI bug 注入和数据集生成框架  
> 为视觉缺陷检测模型提供高质量的训练数据

---

## 📌 项目概述

### 核心问题
- **现状**：手工标注 UI bug 数据集耗时且成本高昂
- **挑战**：MLLM 直接从完整截图生成代码时存在 **85% 元素遗漏**、**12.7% 布局错位**、**2.6% 视觉失真** 等系统性失败
- **方案**：自动化注入多种类型的 bug，生成配对的 normal/buggy 图像集合，用于训练视觉缺陷检测模型

### 关键特性

| 特性 | 说明 |
|------|------|
| **9+3 种 Bug 类型** | 覆盖布局、样式、内容三大类缺陷 |
| **自动化注入** | 基于 Selenium 和 JavaScript，无需手工标注 |
| **配对样本** | 每个 bug 对应一对 normal/buggy 图像和元数据 |
| **多维验证** | RMS + SSIM + 直方图 + 边缘差异，确保样本质量 |
| **实时调试** | DEBUG 模式下可视化缺陷位置和效果 |
| **可扩展架构** | 支持新增 bug 类型和验证策略 |

---

## 🎯 现状与成果

### 已实现的 9 种 Bug 类型

| # | Bug 类型 | 实现方式 | 视觉特征 | 难度 |
|---|---------|---------|---------|------|
| 1 | **Layout_Overlap** | CSS `transform: translate()` | 元素与周围内容重叠 | ⭐ 低 |
| 2 | **Element_Missing** | CSS `visibility: hidden` | 元素消失，留下空白 | ⭐ 低 |
| 3 | **Text_Overflow** | 文本注入长字符串 | 文本超出容器边界 | ⭐ 低 |
| 4 | **Broken_Image** | `img.src = "invalid"` | 图片无法加载 | ⭐ 低 |
| 5 | **Layout_Alignment** | CSS `text-align` 变更 | 对齐错误（左→右等） | ⭐⭐ 中 |
| 6 | **Layout_Spacing** | margin/padding 随机修改 | 间距不一致 | ⭐⭐ 中 |
| 7 | **Data_Format_Error** | 替换数字/日期格式 | 显示格式异常 | ⭐⭐ 中 |
| 8 | **Style_Color_Contrast** | 背景色强行改为相似色 | 对比度不足，看不清 | ⭐⭐ 中 |
| 9 | **Style_Size_Inconsistent** | font-size/width 随机修改 | 尺寸不一致 | ⭐⭐⭐ 高 |

### 高优先级新增类型（待实现）

| Bug 类型 | 视觉特征 | 优先级 | 理由 |
|---------|---------|--------|------|
| **Empty_Layout** | 大面积空白区域 | 🔴 高 | 高频缺陷（对应 MLLM 85% 遗漏问题） |
| **Letter_Spacing_Issue** | 字母间距过大/过小 | 🔴 高 | 独特视觉特征，易验证 |
| **Unnecessary_Scroll** | 出现意外滚动条 | 🔴 高 | 响应式布局失效的典型表现 |

---

## 🚀 快速开始

### 环境配置

```bash
# 安装依赖
pip install selenium pillow webdriver-manager

# 检查 Chrome 浏览器已安装
# ChromeDriver 会自动下载到合适位置
```

### 基本使用

```bash
# 1. 运行数据生成
python auto_injector.py

# 2. 生成训练数据（自然语言报告）
python templates.py generate

# 3. 查看输出
ls dataset_injected/
  ├── images/visual/       # 截图对（normal + buggy）
  ├── raw_metadata/        # 原始 JSON
  └── training_data/       # SFT 训练数据
```

### 配置说明

```python
# ============ 核心配置 ============

DEBUG_MODE = True
# True  = 调试模式：保留所有样本，添加红框标记，便于肉眼检查
# False = 生产模式：自动过滤低质量样本（RMS < 2.0）

VIEWPORT_SIZE = (1920, 1080)
# 模拟视口大小，影响元素候选集和布局

TARGET_URLS = [
    "https://www.w3.org/",           # 稳定的文档站
    "https://docs.python.org/3/",    # 类似的标准 HTML 结构
    # ...添加更多
]
# 建议选择"长期稳定"的站点（文档、门户、wiki），避免商业网站（频繁变更）
```

---

## 📊 数据集输出格式

### 文件结构

```
dataset_injected/
├── images/                        # 统一存放所有图片
│   ├── visual/                    # 视觉类 Bug 图片
│   │   ├── {uuid}_normal.png      # 正常截图
│   │   └── {uuid}_buggy.png       # bug 注入后的截图
│   └── interaction/               # 交互类 Bug 图片序列（未来支持）
│       ├── {uuid}_step1_start.png # 初始状态
│       ├── {uuid}_step1_act.png   # 动作标注图
│       └── {uuid}_step2_end.png   # 结果状态
├── labels/                        # YOLO 格式标签（可选）
│   └── {uuid}.txt
├── raw_metadata/                  # 原始元数据（中间产物）
│   └── {uuid}.json
└── training_data/                 # 最终训练数据（SFT 格式）
    ├── train_sft.jsonl            # 训练集
    └── test_sft.jsonl             # 测试集
```

### 元数据格式

**raw_metadata/{uuid}.json** 格式：

```json
{
  "id": "abc12345",
  "url": "https://www.w3.org/",
  "bug_type": "Layout_Overlap",
  "viewport": { "x": 1920, "y": 1080 },
  
  "normal_image": "images/visual/abc12345_normal.png",
  "buggy_image": "images/visual/abc12345_buggy.png",
  
  "element_info": {
    "tag": "button",
    "class": "nav-link",
    "id": "submit",
    "bbox": { "x": 150, "y": 200, "width": 100, "height": 40 }
  },
  
  "bug_info": {
    "type": "Layout_Overlap",
    "offset_x": 50,
    "offset_y": -40,
    "description": "元素向右下方偏移"
  },
  
  "validation": {
    "rms_diff": 15.32,
    "ssim_diff": 0.18,
    "hist_diff": 450,
    "edge_diff": 320,
    "is_valid": true
  },
  
  "timestamp": "2025-01-06T10:30:45Z"
}
```

**training_data/train_sft.jsonl** 格式（用于 MLLM 微调）：

```jsonl
{"id": "abc12345", "image": "images/visual/abc12345_buggy.png", "conversations": [
  {"from": "human", "value": "请分析这个网页截图，判断是否存在 UI 缺陷，并给出详细的问题描述。"},
  {"from": "assistant", "value": "检测到布局重叠缺陷：导航栏按钮在坐标(150, 200)位置与周围内容发生遮挡。\n\n影响用户体验，导致内容难以阅读或交互受阻。\n\n建议检查该元素的 CSS 定位属性（transform/position），确保不与其他元素产生遮挡。"}
], "metadata": {"bug_type": "Layout_Overlap", "url": "https://www.w3.org/", "bbox": {...}}}
```

---

## 🔧 工作流程

### 单次迭代步骤

```
1. load_page(url)
   └─ 加载网页，智能等待渲染完成

2. get_candidate_elements()
   └─ 查找可注入元素（过滤轮播、广告、幽灵元素）

3. 记录初始截图
   ├─ normal_bbox = 获取元素坐标
   └─ screenshot("normal_*.png")

4. inject_bug(element, bug_type)
   ├─ 执行缺陷注入脚本
   └─ 返回修改后的 bbox

5. 添加调试覆盖层（仅 DEBUG 模式）
   └─ 在页面上方绘制红色矩形标记缺陷位置

6. 记录缺陷截图
   └─ screenshot("buggy_*.png")

7. 多维验证
   ├─ RMS / SSIM / 直方图 / 边缘差异
   └─ 生产模式下：RMS < 2.0 则丢弃

8. 保存元数据
   ├─ normal_<uuid>.png + buggy_<uuid>.png
   ├─ <uuid>.json（元数据）
   └─ <uuid>.txt（标签）

9. 重置页面
   └─ 轻量重置（恢复滚动位置、移除注入脚本）

10. 重复 2-9（同一页面生成多对样本）
```

---

## 📈 质量控制

### 验证机制

#### 1. RMS 差异（像素级）
```python
# 计算两图像的像素均方根差异
# RMS > 2.0 = 注入有效（差异明显）
# RMS < 2.0 = 可能失败（差异太小，丢弃）
```

#### 2. SSIM 差异（结构相似性）
```python
# 0 = 完全相同，1 = 完全不同
# SSIM_diff > 0.1 = 注入有效
```

#### 3. 直方图差异（颜色分布）
```python
# 颜色分布的总差异
# hist_diff > 500 = 颜色明显变化（如 Color_Contrast bug）
```

#### 4. 边缘差异（位置变化）
```python
# Canny 边缘检测后的像素不同数
# edge_diff > 200 = 位置明显移动（如 Layout_Overlap bug）
```

### 样本过滤

**DEBUG 模式**：保留全部样本（便于肉眼检查）

**生产模式**：自动丢弃不满足条件的样本
```python
if validation['rms_diff'] < 2.0:
    print(f"❌ 样本 {sample_id} RMS 差异过小，丢弃")
    # 移除 normal_*.png, buggy_*.png, *.json, *.txt
```

---

## 🎓 架构设计

### 核心类与方法

#### AutoInjector 类

| 方法 | 功能 | 说明 |
|------|------|------|
| `load_page(url)` | 加载网页 | 智能等待：DOM ready + 额外延迟 + 懒加载触发 |
| `get_candidate_elements()` | 查找可注入元素 | 多维过滤：尺寸、坐标、轮播、幽灵元素 |
| `inject_bug(element, bug_type)` | 执行注入 | 返回 (success, bug_info) |
| `pause_animations()` | 冻结动画 | 禁用 animation/transition，减少重排 |
| `scroll_to_element(element)` | 滚动到元素 | 保证元素在视口内 |
| `_add_debug_overlay(bbox)` | 绘制调试框 | 仅 DEBUG 模式有效 |
| `_calculate_image_diff()` | 计算差异 | RMS 和其他指标 |

#### 关键设计

1. **视口锁定**
   - 记录每对截图的 scroll_y 位置
   - 确保 normal 和 buggy 在同一滚动位置

2. **元素候选过滤**
   - ❌ 跳过：轮播、广告、幽灵元素、过小/过大元素
   - ✅ 保留：可见、合理尺寸、有内容的元素

3. **动画冻结**
   - 注入前调用 `pause_animations()` 禁用全局 animation
   - 避免重排导致元素位置动态变化

4. **双模式运行**
   - **DEBUG = True**：保留所有样本，便于调试（红框标记）
   - **DEBUG = False**：自动过滤低质量样本（基于 RMS）

---

## 🛠️ 常见问题与故障排除

### Q1: 某个网站加载失败怎么办？
```
A: 检查：
1. URL 是否正确（https:// 不能少）
2. 网络连接是否正常
3. 站点是否被 robots.txt 限制（改用其他源）

建议站点特征：
✅ 响应快（< 5s）
✅ 结构稳定（长期不变）
✅ 无反爬虫机制
❌ 避免：商业站、登录墙、频繁变更
```

### Q2: 注入后截图没有变化怎么办？
```
A: 调整 inject_bug() 中的注入参数：
- Layout_Overlap: 增加偏移量（从 ±50px → ±100px）
- Element_Missing: 确认元素确实被 visibility: hidden
- Text_Overflow: 增加字符串长度

或切换到 DEBUG_MODE = True，观察红框位置
```

### Q3: RMS 差异总是过小怎么办？
```
A: 可能原因：
1. 网站背景单色，注入改变小
2. bug 类型不适合当前元素（如在空白区注入 Text_Overflow）
3. 注入脚本被 CSS 样式覆盖（如 !important）

改进：
- 增加注入强度（translate 从 50px → 100px）
- 选择更适合的元素（按钮 > 空 div）
- 使用 !important 确保脚本生效
```

### Q4: 如何生成大规模数据集（10K+）？
```
A: 参考 DATASET_COMBINED_PLAN.md 的优化方案：
1. 实现批量注入：一次加载生成 5 对样本（分摊加载成本）
2. 轻量重置：避免完整 reload，仅清理注入脚本
3. 浏览器池：复用 driver 实例，避免重复启动 Chrome
4. 并发处理：ThreadPoolExecutor + driver pool
5. 分档等待：文档站 2s，新闻站 5s，电商站 10s

预期：当前 3s/样本 → 优化后 0.5-1s/样本
```

---

## 📚 相关文档

| 文档 | 用途 |
|------|------|
| [IMPROVEMENTS.md](IMPROVEMENTS.md) | 改进措施列表（基于论文洞察 + 代码分析） |
| [templates.py](templates.py) | 自然语言报告生成模板库 |
| [auto_injector.py](auto_injector.py) | 核心脚本（自动注入实现） |

---

## 🧪 实验与验证

### 推荐实验流程

#### Phase 1: 快速验证（Week 1）
```bash
# 1. 小规模测试（5 个 URL × 100 样本 = 500 样本）
python auto_injector.py

# 2. 人眼抽检 20 张样本，评估：
#    - 红框位置是否准确？
#    - 缺陷是否明显可见？
#    - 有无误标或重复？

# 3. 统计输出：
#    - 总样本数 / 有效样本数 / 失败原因
#    - 各 bug 类型的分布
#    - RMS 差异的分布（应 > 2.0）
```

#### Phase 2: 规模化生成（Week 2-3）
```bash
# 4. 根据反馈调整参数：
#    - 增加 TARGET_URLS（15-20 个站点）
#    - 调整注入强度（元素过滤规则）
#    - 新增 3 种 bug 类型（Empty_Layout 等）

# 5. 生成 5K 正式样本（应耗时 < 4 小时）

# 6. 质量报告：
#    - 各 bug 类型的有效率
#    - RMS/SSIM/直方图分布
#    - 失败案例分析
```

#### Phase 3: 模型训练（Week 4+）
```bash
# 7. 数据集划分（train/val/test = 70/15/15）

# 8. 训练视觉缺陷检测模型
#    - YOLO 或 Faster R-CNN
#    - 输入：图像，输出：bug 类型 + 位置

# 9. 评估：Precision / Recall / F1-Score
#    - 预期：F1 > 0.7（good）
#    - 目标：F1 > 0.8（excellent）

# 10. 分析困难 bug 类型，返回 Phase 2 补充数据
```

---

## 📖 引用与灵感

本项目的思想受到以下工作的启发：

1. **《Divide-and-Conquer: Generating UI Code from Screenshots》**
   - DCGen 框架揭示的 MLLM 三类失败模式（遗漏、失真、错位）
   - 分而治之策略（分片 → 注入 → 组装）的通用性

2. **《How we built UI bug detection from scratch》**（dev.to）
   - UI bug 检测的工业实践
   - 样本多样性的重要性

3. **自适应加载与并发优化**
   - 参考现代 Web 爬虫的最佳实践
   - 站点分档、资源拦截、自适应等待

---

## 📝 许可证

MIT License - 自由使用、修改和分发

---

## 💬 反馈与改进

如有问题或改进建议，欢迎提交 Issue 或 PR：

- 🐛 **Bug Report**：描述问题、复现步骤、预期行为
- 💡 **Feature Request**：新增 bug 类型、优化策略、工具脱敏
- 📊 **Data Sharing**：分享你生成的数据集和实验结果

---

## 📅 项目时间线

| 阶段 | 时间 | 目标 |
|------|------|------|
| **v1.0 基础** | ✅ 完成 | 9 种 bug 类型 + 基础验证 |
| **v1.1 优化** | 🔄 进行中 | 多维验证 + 新增 3 种 bug 类型 |
| **v2.0 规模化** | 📅 计划中 | 并发 + 批量注入 + 跨站点优化 |
| **v2.1 工具化** | 📅 计划中 | Web UI + 数据集管理 + 可视化 |

---

**Last Updated**: 2025-01-06  
**Maintained by**: Research Team
