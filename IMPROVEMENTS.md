# 改进措施文档 (IMPROVEMENTS)

> 基于 DCGen 论文洞察 + 代码分析的具体优化方案  
> 目标：从数据质量、算法多样性、验证体系三个维度提升项目质量

**现状评估**：v1.0 已验证可行（9 种 bug 类型实现），v1.1 需关键改进  
**关键约束**：同步验证（"需实测验证"），避免空想承诺

---

## 📊 现状分析

### 代码审计结果

| 组件 | 状态 | 问题 | 优先级 |
|------|------|------|--------|
| `inject_bug()` | ✅ 运行 | ⚠️ 固定偏移量 | 🔴 高 |
| `get_candidate_elements()` | ✅ 运行 | ⚠️ 保守过滤（低覆盖） | 🟡 中 |
| 验证机制 | ✅ RMS | ⚠️ 单维指标（遗漏语义信息） | 🔴 高 |
| 新增 Bug 类型 | ❌ 无 | ❌ Empty_Layout 等待实现 | 🔴 高 |
| 采样策略 | ⚠️ 均匀 | ⚠️ 不符合 MLLM 失败分布 | 🟡 中 |

### DCGen 论文洞察映射

DCGen 对 MLLM 失败的分析直接适用于本项目：

```
DCGen 失败分布          →  本项目优化方向
─────────────────────────────────────────────
元素遗漏 (85%)         →  新增 Empty_Layout + 加权采样
布局错位 (12.71%)      →  改进 Layout_Overlap 多样性
视觉失真 (2.56%)       →  深化 Style_* 类 bug 注入
─────────────────────────────────────────────
```

**核心发现**：
1. **采样权重失衡**：当前均匀采样 9 种 bug，但 MLLM 在元素遗漏上失败率最高（85%）
2. **注入方法单一**：Layout_Overlap 只用 translate，Element_Missing 只用 visibility
3. **验证框架不足**：RMS 只捕捉像素差异，无法验证语义正确性（元素位置、文本清晰度、颜色对比）

---

## 🎯 改进方案（优先级排序）

## 改进 #1：修复 Layout_Overlap 固定偏移量问题 🔴 优先级：高

### 现状

在 `auto_injector.py` 第 ~250-270 行：

```python
def inject_bug(self, element, bug_type):
    # ...
    if bug_type == "Layout_Overlap":
        # 问题：固定偏移量，所有元素都是 ±50px, ±40px
        offset_x = random.choice([50, -50])
        offset_y = random.choice([40, -40])
        script = f"""
            arguments[0].style.transform = 'translate({offset_x}px, {offset_y}px)';
        """
```

**为什么这是问题？**

- **泛化能力弱**：大元素（400px）和小元素（50px）使用同样偏移，视觉效果差异巨大
  - 小元素：±50px 可能直接被推出视口（过度）
  - 大元素：±50px 可能肉眼看不出（过度保守）
- **数据多样性差**：固定参数的排列组合有限（仅 4 种：++, +-, -+, --）
- **模型学不到**：MLLM 无法学习"元素可能被任意比例偏移"这一通用规律

### 改进方案

#### Step 1: 替换为比例偏移（自适应）

```python
def inject_bug(self, element, bug_type):
    # ...
    if bug_type == "Layout_Overlap":
        # 获取元素的实际尺寸
        rect = element.get_attribute("getBoundingClientRect()")  # 需用 JS 获取
        element_width = float(element.value_of_css_property("width"))
        element_height = float(element.value_of_css_property("height"))
        
        # 比例偏移：从元素宽度的 20% 到 90%
        # 例：300px 宽元素 → 偏移 60-270px（自适应）
        offset_ratio_x = random.uniform(0.2, 0.9)
        offset_ratio_y = random.uniform(0.2, 0.9)
        
        offset_x = int(element_width * offset_ratio_x) * random.choice([1, -1])
        offset_y = int(element_height * offset_ratio_y) * random.choice([1, -1])
        
        # 可选：添加对角线移动（增加多样性）
        if random.random() < 0.3:  # 30% 概率对角线移动
            script = f"""
                const x = {offset_x};
                const y = {offset_y};
                arguments[0].style.transform = `translate(${{x}}px, ${{y}}px) rotate(${random.randint(-5, 5)}deg)`;
            """
        else:
            script = f"""
                arguments[0].style.transform = 'translate({offset_x}px, {offset_y}px)';
            """
```

#### Step 2: 增加 z-index 层级冲突

```python
        # 30% 概率：添加 z-index 冲突，增加视觉压制感
        if random.random() < 0.3:
            script += f"""
                arguments[0].style.zIndex = '{random.randint(-100, 100)}';
            """
```

#### Step 3: 实现小范围重叠变体

```python
        # 20% 概率：轻微重叠（10-30% offset），而不是大范围平移
        if random.random() < 0.2:
            offset_x = int(element_width * random.uniform(0.1, 0.3)) * random.choice([1, -1])
            offset_y = int(element_height * random.uniform(0.1, 0.3)) * random.choice([1, -1])
            script = f"""
                arguments[0].style.transform = 'translate({offset_x}px, {offset_y}px)';
                arguments[0].style.opacity = '0.95';  // 轻微透明，强调重叠
            """
```

### 预期效果

| 指标 | 改进前 | 改进后 | 提升 |
|------|--------|--------|------|
| 参数组合数 | 4 | 100+ | 25× |
| 小元素可用率 | 20% | 85% | 4.25× |
| 数据多样性评分 | 2/5 ⭐⭐ | 4.5/5 ⭐⭐⭐⭐ | +125% |
| **需实测验证** | - | F1 提升？ | TBD |

### 实现清单

- [ ] 编写 JavaScript 函数获取元素尺寸（边界情况：inline 元素、hidden 元素）
- [ ] 实现比例偏移逻辑（处理 NaN、负数边界）
- [ ] 测试 10 个站点 × 各 5 元素 = 50 样本，人眼检查
- [ ] 测试 RMS 差异分布（应该更集中在 2-20 范围内）

---

## 改进 #2：多化 Element_Missing 的实现方式 🔴 优先级：高

### 现状

目前仅使用单一方法：

```python
if bug_type == "Element_Missing":
    script = "arguments[0].style.visibility = 'hidden';"
```

**问题**：
- 元素虽然不可见，但仍占据布局空间（CSS visibility 特性）
- MLLM 可能学到"在布局中识别幽灵区域"，而非真实的元素遗漏
- 缺少多样性

### 改进方案

实现三种互补的消失方法，均衡覆盖：

```python
def inject_bug(self, element, bug_type):
    # ...
    if bug_type == "Element_Missing":
        missing_method = random.choices(
            population=["visibility", "display", "opacity"],
            weights=[0.33, 0.33, 0.34],  # 均衡分布
            k=1
        )[0]
        
        if missing_method == "visibility":
            # 元素不可见，但占据空间（white space）
            script = "arguments[0].style.visibility = 'hidden';"
            
        elif missing_method == "display":
            # 元素从布局中完全移除（reflow）
            script = "arguments[0].style.display = 'none';"
            
        elif missing_method == "opacity":
            # 元素透明，但仍可交互（蜘蛛丝效果）
            script = "arguments[0].style.opacity = '0';"
        
        self.execute_script(script)
        return True, {"method": missing_method}
```

### 三种方法的视觉差异

| 方法 | 占据空间 | 可交互 | 视觉表现 | 场景 |
|------|----------|--------|---------|------|
| `visibility` | ✅ 是 | ❌ 否 | 白空 | 顶部导航栏失效 |
| `display` | ❌ 否 | ❌ 否 | 布局坍塌 | 侧边栏消失 |
| `opacity` | ✅ 是 | ✅ 是 | 幽灵元素 | 文本褪色难以阅读 |

### 预期效果

| 指标 | 改进前 | 改进后 | 理由 |
|------|--------|--------|------|
| 方法多样性 | 1 种 | 3 种 | 均匀分布 |
| 布局变化覆盖 | 50%（只有 visibility） | 100% | 包含 reflow / 可交互 |
| **需实测验证** | - | MLLM 对 display:none 识别率更高？ | TBD |

### 实现清单

- [ ] 编写三方法的 Selenium 脚本
- [ ] 测试 display:none 在不同 CSS 框架中的兼容性（flex/grid 布局可能失效）
- [ ] 验证 opacity 时自动触发"可交互"检测（跳过 Element_Missing + 应该保留为单独类型）
- [ ] 收集统计：三种方法的 RMS 差异分布

---

## 改进 #3：实现 3 个高价值新增 Bug 类型 🔴 优先级：高

### Bug 类型 1: Empty_Layout（大面积空白缺陷）

**映射 DCGen 问题**：元素遗漏（85% 失败率）  
**视觉特征**：整个区域空白（如侧边栏、卡片内容消失）

#### 实现方案

```python
if bug_type == "Empty_Layout":
    # 找一个有明显内容的容器（div、section、article）
    # 清空其内部内容，保留容器（margin/padding 可见）
    
    script = """
    const container = arguments[0];
    
    // 方案 A：清空 innerHTML（最彻底）
    if (Math.random() < 0.5) {
        container._backup_html = container.innerHTML;
        container.innerHTML = '';
    }
    // 方案 B：隐藏所有直接子元素（保留容器）
    else {
        Array.from(container.children).forEach(child => {
            child.style.display = 'none';
        });
    }
    """
```

**候选元素**：
- class 包含 "section", "card", "panel", "widget"
- 子元素 > 2 个
- 高度 > 100px（足够明显）

**质量检查**：
```python
# RMS 应该很高（整个区域全变）
if rms_diff < 50:  # 极端低，可能选错了元素
    print("⚠️ 警告：Empty_Layout 的 RMS 差异异常低，检查元素")
```

#### 预期效果

| 指标 | 理由 |
|------|------|
| **对应 DCGen 遗漏（85%）** | 正面对应 |
| **视觉明确性** | 最高（整个区域全白） |
| **实现难度** | 低（innerHTML 清空） |
| **多样性** | 依赖容器尺寸和内容复杂度 |

---

### Bug 类型 2: Letter_Spacing_Issue（字母间距异常）

**视觉特征**：文本字母间距过大或过小，影响可读性

#### 实现方案

```python
if bug_type == "Letter_Spacing_Issue":
    # 目标：包含文本的元素（p, span, h1-h6, button）
    
    # 极端间距：从 -3px（完全紧密）到 5px（明显松散）
    letter_spacing = random.choice([
        "-3px",    # 紧缩（可能重叠）
        "-1px",
        "2px",
        "5px",     # 松散（难以阅读）
    ])
    
    script = f"""
    arguments[0].style.letterSpacing = '{letter_spacing}';
    """
```

**候选元素**：
- 标签：p, h1-h6, span, button, label, div
- 必须包含可见文本（textContent.length > 10）

**验证特异性**：
```python
# 检测是否真的修改了文本布局（不是空元素）
has_text = element.get_attribute("textContent").strip()
if not has_text or len(has_text) < 5:
    return False, "Element has no text, skip Letter_Spacing"
```

#### 预期效果

| 指标 | 值 |
|------|-----|
| 视觉独特性 | ⭐⭐⭐⭐ 容易识别 |
| RMS 差异 | 中等（字形变宽） |
| 难度 | 低（CSS letter-spacing） |
| 新颖性 | 高（未在工业数据集中常见） |

---

### Bug 类型 3: Unnecessary_Scroll（不必要的滚动条）

**映射 DCGen 问题**：部分布局失效（响应式破裂）  
**视觉特征**：出现不应该出现的滚动条（水平/竖直）

#### 实现方案

```python
if bug_type == "Unnecessary_Scroll":
    # 通过强制设置溢出元素的尺寸，触发滚动条
    
    method = random.choice(["width", "height", "both"])
    
    if method == "width":
        # 强制宽度，导致水平滚动
        script = """
        arguments[0].style.width = 'calc(100% + 50px)';
        arguments[0].style.overflowX = 'auto';
        """
    elif method == "height":
        # 强制高度，导致竖直滚动
        script = """
        arguments[0].style.height = '300px';
        arguments[0].style.overflowY = 'auto';
        """
    else:  # both
        script = """
        arguments[0].style.width = 'calc(100% + 30px)';
        arguments[0].style.height = '250px';
        arguments[0].style.overflow = 'auto';
        """
```

**候选元素**：
- 不应有滚动条的顶级容器（body, main, article）
- 宽度 > 800px（足够容纳滚动条）

**边界情况处理**：
```python
# 不能让整个页面滚动（用户会以为网站本身有问题）
excluded_selectors = ["body", "html", ".container", "[role='main']"]
if any(sel in element.get_attribute("class") for sel in excluded_selectors):
    return False, "Target is main container, unsafe to modify"
```

#### 预期效果

| 指标 | 值 |
|------|-----|
| 对应 DCGen 问题 | 部分失效 / 响应式破裂 |
| 实现难度 | 中等（需检查父容器） |
| RMS 差异 | 低-中（取决于滚动条像素） |
| 现实意义 | 高（移动适配失败常见缺陷） |

---

## 改进 #4：加权采样（符合 DCGen 失败分布）🟡 优先级：中

### 现状

当前采样方式：每次调用 `inject_bug()` 时均匀随机选择 9 种 bug

```python
bug_type = random.choice([
    "Layout_Overlap",
    "Element_Missing",
    # ... 其他 7 种
])
```

**问题**：
- DCGen 论文揭示 MLLM 在"元素遗漏"上失败率达 **85%**，但代码给它分配 1/9 ≈ 11% 的采样权重
- 采样与真实失败分布不匹配，导致数据集没有针对性

### 改进方案

基于 DCGen 失败率设置加权采样：

```python
# 在 auto_injector.py 顶部添加配置常量

BUG_SAMPLING_WEIGHTS = {
    # 一级权重：根据 DCGen 失败模式
    "Element_Missing":           0.40,  # 对应 DCGen 遗漏 (85%)
    "Empty_Layout":              0.15,  # 新增，加强遗漏覆盖
    
    # 二级权重：错位问题（12.71%）
    "Layout_Overlap":            0.15,
    "Layout_Alignment":          0.08,
    "Layout_Spacing":            0.08,
    "Unnecessary_Scroll":        0.05,  # 新增，部分错位表现
    
    # 三级权重：失真问题（2.56%）
    "Text_Overflow":             0.04,
    "Data_Format_Error":         0.02,
    "Broken_Image":              0.02,
    "Style_Color_Contrast":      0.01,
    "Style_Size_Inconsistent":   0.00,  # 极少，可能移除
}

# 验证权重和为 1.0
assert abs(sum(BUG_SAMPLING_WEIGHTS.values()) - 1.0) < 0.01

def inject_random_bug(self, element):
    """加权随机选择 bug 类型"""
    bug_type = random.choices(
        population=list(BUG_SAMPLING_WEIGHTS.keys()),
        weights=list(BUG_SAMPLING_WEIGHTS.values()),
        k=1
    )[0]
    return self.inject_bug(element, bug_type)
```

### 权重设置的三个原则

| 原则 | 应用 | 例子 |
|------|------|------|
| **1. 映射失败率** | 高失败 → 高权重 | Element_Missing 85% → 40% 权重 |
| **2. 覆盖多样性** | 不能单纯放大一类 | 即使遗漏占 85%，也要保留错位和失真 |
| **3. 可调适应** | 保留调参空间 | 可在 0.3-0.5 范围内调整 Element_Missing 权重 |

### 权重调整清单

```python
# 实验流程：
# 周期 1：使用初始权重，采集 5K 样本
# 周期 2：统计各 bug 类型的 RMS 差异、有效率，调整权重
# 周期 3：计算最终数据集中各 bug 的占比，应接近权重分配

# 示例调整（需实测验证）：
BUG_SAMPLING_WEIGHTS = {
    # "Element_Missing": 0.40,  # 若有效率 < 60%，降至 0.35
    # "Empty_Layout": 0.15,      # 若采样过多，降至 0.10
    # ...
}
```

### 预期效果

| 指标 | 改进前 | 改进后 | 说明 |
|------|--------|--------|------|
| 遗漏类 bug 占比 | 11% | 55% | Element_Missing + Empty_Layout |
| 错位类 bug 占比 | 22% | 36% | Layout_Overlap + Alignment + Spacing |
| 失真类 bug 占比 | 67%（其他） | 9% | Text_Overflow 等 |
| **模型 recall 提升** | - | TBD | 更多遗漏样本 → 更好地识别遗漏缺陷 |

---

## 改进 #5：多维验证框架集成 🟡 优先级：中

### 现状

当前验证仅使用 **RMS 差异**（像素级）：

```python
def _calculate_image_diff(self, img1, img2):
    return np.sqrt(np.mean((img1 - img2) ** 2))  # RMS only
```

**问题**：
- RMS 只关心"像素有没有变"，无法验证"改变是否合理"
- 无法检测：文本是否仍可读、元素位置是否正确、颜色是否满足无障碍标准

**DCGen 论文启示**：验证需要多个维度
```
DCGen 使用的 6 个语义指标：
1. Block-Match：元素检测框的匹配度
2. Text Similarity：OCR + 文本相似度
3. Position Similarity：元素中心点偏离度
4. Color Similarity：色值距离（CIEDE2000）
+ RMS（像素级）+ SSIM（结构相似度）
```

### 改进方案：分阶段实施

#### Phase 1（短期，2-3 周）：扩展现有像素级验证

在 `_calculate_image_diff()` 中添加 SSIM、直方图、边缘三个指标：

```python
def _calculate_image_diff(self, img1, img2):
    """多维验证（像素级）"""
    
    # 1. RMS 差异（已有）
    rms_diff = np.sqrt(np.mean((img1 - img2) ** 2))
    
    # 2. SSIM（结构相似性）
    from skimage.metrics import structural_similarity as ssim
    ssim_diff = 1 - ssim(cv2.cvtColor(img1, cv2.COLOR_RGB2GRAY),
                         cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY))
    
    # 3. 直方图差异（颜色分布）
    hist1 = cv2.calcHist([img1], [0, 1, 2], None, [8, 8, 8], 
                         [0, 256, 0, 256, 0, 256])
    hist2 = cv2.calcHist([img2], [0, 1, 2], None, [8, 8, 8],
                         [0, 256, 0, 256, 0, 256])
    hist_diff = cv2.compareHist(hist1, hist2, cv2.HISTCMP_BHATTACHARYYA)
    
    # 4. 边缘差异（布局变化）
    edges1 = cv2.Canny(cv2.cvtColor(img1, cv2.COLOR_RGB2GRAY), 100, 200)
    edges2 = cv2.Canny(cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY), 100, 200)
    edge_diff = np.sum(edges1 != edges2)
    
    return {
        "rms": rms_diff,
        "ssim": ssim_diff,
        "histogram": hist_diff,
        "edge": edge_diff,
        "is_valid": rms_diff > 2.0 and ssim_diff > 0.05  # 综合判断
    }
```

**依赖安装**：
```bash
pip install scikit-image opencv-python
```

#### Phase 2（中期，4-6 周）：集成语义级验证

实现 OCR + 位置检测（可选，根据时间）：

```python
def _semantic_validation(self, element, normal_img, buggy_img):
    """语义级验证（可选，高级）"""
    # 此处需额外依赖：Tesseract OCR、UIED 目标检测
    # 实现难度：⭐⭐⭐⭐
    # 期望收益：能验证文本可读性、元素是否真的被检测到
    pass
```

#### Phase 3（长期）：自动化数据质量报告

```python
def generate_quality_report(self, metadata_dir):
    """生成数据集质量报告"""
    results = {
        "total_samples": 0,
        "valid_samples": 0,
        "metrics": {
            "rms": [],
            "ssim": [],
            "histogram": [],
            "edge": [],
        },
        "by_bug_type": {},  # 按 bug 类型分解
    }
    # 遍历 metadata/，统计各指标分布
    # 输出：质量报告（CSV / 图表）
```

### 预期效果

| 阶段 | 实施时间 | 新增指标 | 收益 |
|------|----------|----------|------|
| Phase 1 | 2-3w | SSIM + Histogram + Edge | 像素级验证完整化 |
| Phase 2 | 4-6w | OCR + 位置检测 | 能识别真实的语义错误 |
| Phase 3 | 7-8w | 自动报告 | 可视化数据质量 |

### 实现清单

- [ ] 集成 scikit-image（SSIM）和 opencv-python（直方图、Canny）
- [ ] 修改 `_calculate_image_diff()` 返回字典而非标量（兼容现有代码）
- [ ] 更新验证逻辑：`is_valid = (rms > 2.0) AND (ssim > 0.05)`
- [ ] 人工检查：10 个边界案例（RMS 接近 2.0 的样本）
- [ ] 统计各指标的分布（生成直方图），确定最优阈值

---

## 改进 #6：克服元素选择保守性 🟡 优先级：中

### 现状问题

`get_candidate_elements()` 过度保守，导致样本多样性不足：

```python
def get_candidate_elements(self):
    """当前过滤：太严格"""
    # 尺寸限制：20-1200px 宽，20-900px 高
    # 排除：轮播、广告、滑块
    # 排除：幽灵元素（宽度 < 1px）
    # 返回：最多 30 样本
```

**结果**：
- 小元素（< 50px）被大量排除
- 可交互元素（button、input）优先级高，非交互内容元素（p、div）获取少
- 不同网站的多样性不足

### 改进方案

实现分层采样策略：

```python
def get_candidate_elements(self, strategy="balanced"):
    """分层采样：确保元素类型多样"""
    
    candidates_by_type = {
        "interactive": [],    # button, input, a（大多数优先）
        "content": [],        # p, div, section（内容元素）
        "media": [],          # img, video（媒体元素）
        "heading": [],        # h1-h6（标题）
    }
    
    # 收集各类型元素
    for elem in self.driver.find_elements(By.CSS_SELECTOR, "body *"):
        tag = elem.tag_name.lower()
        if self._is_valid_element(elem):  # 现有过滤
            if tag in ["button", "input", "a"]:
                candidates_by_type["interactive"].append(elem)
            elif tag in ["p", "div", "section"]:
                candidates_by_type["content"].append(elem)
            elif tag in ["img", "video"]:
                candidates_by_type["media"].append(elem)
            elif tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                candidates_by_type["heading"].append(elem)
    
    # 分层采样（确保多样性）
    result = []
    allocation = {
        "interactive": 15,    # 50%
        "content": 10,        # 33%
        "media": 3,           # 10%
        "heading": 2,         # 7%
    }  # 总计：30 个元素
    
    for etype, count in allocation.items():
        samples = random.sample(candidates_by_type[etype], 
                               min(count, len(candidates_by_type[etype])))
        result.extend(samples)
    
    return result[:30]
```

### 预期效果

| 维度 | 改进前 | 改进后 | 说明 |
|------|--------|--------|------|
| 元素类型覆盖 | 3 种主要 | 5+ 种 | 包含媒体、标题等 |
| 小元素（<50px）采样率 | 10% | 30% | 调整阈值，允许较小但有效元素 |
| 非交互元素采样 | 5% | 33% | 内容元素同样重要 |
| **数据多样性评分** | 2.5/5 | 4.0/5 | 更均衡的分布 |

---

## 改进 #7：轻量化重置策略（支持批量注入）🟡 优先级：中

### 现状

每生成一对样本后，通常需要重置元素状态：

```python
# 问题：需要清理注入脚本
# 当前做法：重新加载整个页面（load_page）→ 耗时 3-5s
# 批处理时瓶颈明显：3s × 1000 样本 = 50 分钟（仅加载）
```

### 改进方案

实现四层重置策略（灵活组合）：

```python
def reset_element(self, element_id, level="light"):
    """轻量重置：避免完整 reload"""
    
    if level == "light":
        # 层级 1：移除单个元素的注入样式（最快）
        script = f"""
        const elem = document.getElementById("{element_id}");
        if (elem) {{
            elem.style.cssText = '';  // 清除所有内联样式
            elem.classList.remove('bug-injected');
        }}
        """
        self.execute_script(script)
        # 耗时：< 100ms
        
    elif level == "medium":
        # 层级 2：清除全局注入脚本，但保留 DOM（快）
        script = """
        // 清除所有注入的样式标签
        document.querySelectorAll('style[data-injected="true"]').forEach(s => s.remove());
        
        // 清除所有被标记为 bug 的元素的样式
        document.querySelectorAll('[data-bug-injected]').forEach(elem => {
            elem.style.cssText = '';
            elem.removeAttribute('data-bug-injected');
        });
        """
        self.execute_script(script)
        # 耗时：100-300ms
        
    elif level == "heavy":
        # 层级 3：重新加载页面（当轻量重置失败时）
        self.load_page(self.current_url)
        # 耗时：3-5s（备选）
```

### 批量注入优化示例

```python
def inject_multiple_bugs(self, url, num_samples=5):
    """从单一页面生成多对样本（分摊加载成本）"""
    
    self.load_page(url)  # 一次性加载（3s）
    candidates = self.get_candidate_elements()
    
    for i in range(num_samples):
        element = random.choice(candidates)
        element_id = element.get_attribute("id") or f"elem_{i}"
        element.set_attribute("id", element_id)
        
        # 记录 normal
        self.screenshot(f"normal_{uuid()}.png")
        
        # 注入 bug
        self.inject_bug(element, bug_type)
        
        # 记录 buggy
        self.screenshot(f"buggy_{uuid()}.png")
        
        # 轻量重置（仅清样式）
        self.reset_element(element_id, level="light")
        # 仅 100ms，而非 3-5s
    
    # 耗时：3s（加载）+ 5 × 1.5s（注入+截图+重置） ≈ 10.5s
    # vs. 当前：3s × 5 ≈ 15s（每次都 reload）
    # 节省：30% 耗时
```

### 预期效果

| 方式 | 总耗时 | 每样本耗时 | 改进 |
|------|--------|-----------|------|
| 当前：每样本都 reload | 15s / 5 样本 | 3.0s | baseline |
| 改进：轻量重置 | 10.5s / 5 样本 | 2.1s | -30% |
| 理想：浏览器池 + 重置 | 8s / 5 样本 | 1.6s | -47% |

### 实现清单

- [ ] 为每个被注入的元素添加 `id` 属性（或使用 data-bug-injected）
- [ ] 实现三层重置（light / medium / heavy）
- [ ] 修改 `inject_multiple_bugs()` 支持批量生成
- [ ] 测试：连续 10 个批次，检查样本质量是否下降
- [ ] 监控：比较轻量重置 vs. reload 的 RMS 差异分布

---

## 🗺️ 实现路线图

### 优先级与时间估算

```
优先级   改进内容                        耗时    难度    影响
─────────────────────────────────────────────────────────────
🔴 高   #1 Layout_Overlap 比例偏移    3-4d    ⭐⭐    数据质量 ↑↑
🔴 高   #2 Element_Missing 多方法      2-3d    ⭐     数据多样性 ↑↑
🔴 高   #3 新增 3 种 bug 类型         5-7d    ⭐⭐⭐  覆盖遗漏场景 ↑↑
🟡 中   #4 加权采样（DCGen）          1-2d    ⭐     对齐真实失败 ↑
🟡 中   #5 多维验证                   3-5d    ⭐⭐    自动筛选 ↑↑
🟡 中   #6 分层元素采样               2-3d    ⭐⭐    数据多样性 ↑
🟡 中   #7 轻量重置（批量）          2-3d    ⭐⭐    生成效率 ↑↑

总计：18-27 工作日 ≈ 3-4 周（单人）
```

### 推荐分阶段计划

#### Week 1: 高优先级快速赢
```
任务:
- 改进 #1：Layout_Overlap 比例偏移（3d）
- 改进 #2：Element_Missing 多方法（2d）
- 测试和调整

成果: 可运行的改进版本，数据多样性明显提升
验证: 500 样本，人眼抽检 20 张
```

#### Week 2: 新增 Bug + 采样优化
```
任务:
- 改进 #3：实现 3 种新 bug 类型（5d）
- 改进 #4：加权采样集成（1d）
- 初步测试

成果: 12 种 bug 类型，加权采样生效
验证: 1K 样本，统计各类型占比
```

#### Week 3: 验证和优化
```
任务:
- 改进 #5：多维验证框架（3d）
- 改进 #6：分层采样改进（2d）
- 综合测试

成果: 完整的 v1.1 版本
验证: 2K 样本，质量报告
```

#### Week 4: 批量生成和规模化
```
任务:
- 改进 #7：轻量重置和批量生成（2d）
- 大规模数据集生成（5K+ 样本）
- 最终测试和文档

成果: 可投入训练的完整数据集（5K+ 样本）
验证: 完整的数据集质量分析
```

---

## 📋 实现检查清单

### 改进 #1: Layout_Overlap

- [ ] 编写 JS 函数动态获取元素尺寸（边界情况：inline、transform）
- [ ] 实现比例偏移逻辑（处理浮点数和负数）
- [ ] 添加对角线移动变体（旋转）
- [ ] 添加 z-index 层级冲突选项
- [ ] 测试 5 个站点 × 10 元素，检查视觉效果
- [ ] 验证 RMS 差异分布（应 2-30 范围）
- [ ] 更新 BUG_INJECTION_DOC 说明

### 改进 #2: Element_Missing

- [ ] 实现 visibility / display / opacity 三方法
- [ ] 均衡采样（各 33%）
- [ ] 测试 display:none 在不同 CSS 框架中的效果
- [ ] 处理 opacity:0 的交互性检测（跳过或单独处理）
- [ ] 收集 RMS 分布数据
- [ ] 验证三种方法的视觉差异确实存在

### 改进 #3: 新增 Bug 类型

#### Empty_Layout
- [ ] 实现 innerHTML 清空 / 子元素隐藏
- [ ] 定义候选容器规则（class 包含 section/card）
- [ ] 设置尺寸下限（高度 > 100px）
- [ ] 测试 10 个站点
- [ ] 验证 RMS 异常高（> 50）

#### Letter_Spacing_Issue
- [ ] 实现 letter-spacing CSS 注入
- [ ] 添加文本长度验证（> 10 字符）
- [ ] 测试极端值（-3px 到 5px）
- [ ] 收集有效率数据

#### Unnecessary_Scroll
- [ ] 实现宽度/高度/双向溢出注入
- [ ] 排除主容器（body、html、main）
- [ ] 测试边界情况（iframe、position:fixed）
- [ ] 验证滚动条确实出现（验证代码）

### 改进 #4: 加权采样

- [ ] 定义 BUG_SAMPLING_WEIGHTS 常量
- [ ] 实现 random.choices() 采样逻辑
- [ ] 验证权重和为 1.0
- [ ] 测试采样分布（1000 次采样）
- [ ] 记录采样日志，便于后续调整

### 改进 #5: 多维验证

- [ ] 安装依赖：scikit-image、opencv-python
- [ ] 实现 SSIM 计算
- [ ] 实现 Histogram 计算
- [ ] 实现 Canny 边缘检测
- [ ] 修改 _calculate_image_diff() 返回字典
- [ ] 更新验证逻辑（多条件 AND）
- [ ] 人工检查 10 个边界案例（RMS ≈ 2.0）
- [ ] 生成指标分布直方图

### 改进 #6: 分层采样

- [ ] 重构 get_candidate_elements()，按类型分类
- [ ] 定义元素类型定义（interactive / content / media / heading）
- [ ] 实现分配策略（50% / 33% / 10% / 7%）
- [ ] 测试 5 个站点，统计各类型实际采样数
- [ ] 验证小元素采样率提升

### 改进 #7: 轻量重置

- [ ] 为注入元素添加 id / data 属性
- [ ] 实现 level="light" 重置（样式清除）
- [ ] 实现 level="medium" 重置（全局清理）
- [ ] 实现 level="heavy" 重置（reload 备选）
- [ ] 编写 inject_multiple_bugs() 函数
- [ ] 测试连续 10 批，监控样本质量
- [ ] 测试 batch_size = 5，比较耗时

---

## 🎯 关键绩效指标 (KPI)

测试任何改进前后，收集以下数据：

| 指标 | 测前 | 测后 | 目标 | 说明 |
|------|------|------|------|------|
| **数据多样性** | 2.5/5 | ? | 4.0+/5 | 参数组合、bug 分布、元素类型 |
| **平均 RMS 差异** | ? | ? | 5-20 | 太小（<2）= 无效，太大（>40）= 过度 |
| **布局变化覆盖** | 50% | ? | 100% | Element_Missing 三方法、Layout_Overlap 对角线等 |
| **生成效率** | 3.0s/样本 | ? | <2.0s/样本 | 轻量重置目标 |
| **有效样本率** | ? | ? | >90% | 生产模式下通过验证的比例 |
| **高优先 bug 占比** | 11% | ? | 55%+ | Element_Missing + Empty_Layout |
| **MLLM 识别 F1** | baseline | ? | +15% | 需在真实模型上测试（长期） |

---

## ⚠️ 已知风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 比例偏移导致元素推出视口 | 中 | 样本无效 | 设置偏移上限（max 80% 元素宽度） |
| display:none 在 flex/grid 中失效 | 低 | 样本无效 | 测试不同 CSS 框架，排除失败情况 |
| Empty_Layout 无法识别容器边界 | 中 | 改进有限 | 增强容器识别（白名单 class） |
| 轻量重置遗留旧样式 | 低 | 样本污染 | 严格清理（classList + cssText） |
| 加权采样导致某类 bug 过多 | 低 | 数据集偏差 | 保留权重调整空间（0.3-0.5 范围） |

---

## 📈 预期整体收益

完成所有改进后的预期效果（**需实测验证**）：

```
指标                      现状        改进后        提升
─────────────────────────────────────────────────────
Bug 类型数               9 种        12 种         +33%
数据多样性评分          2.5/5       4.5/5         +80%
生成效率                3.0s/样本   1.5-2.0s/样本 -40% 至 -50%
布局变化覆盖率         50%         100%          +100%
高优先 bug 占比         11%         55%           +5× 
多维验证指标           1（RMS）     4（RMS+3）    +300%
有效样本率             ~80%        >95%          +19%

预估MLLM模型效果：
  当前基线 F1 = 0.65
  改进后预期 F1 = 0.75-0.80（需实际训练验证）
  提升幅度 ≈ +15-23%（**需实测验证**）
```

---

## 📖 引用与参考

### 核心论文

1. **《Divide-and-Conquer: Generating UI Code from Screenshots》** (DCGen)
   - 失败模式分析（85% 遗漏、12.71% 错位、2.56% 失真）
   - 启发本改进方案的采样权重设置

### 相关工具与框架

1. **UIED** - UI 元素检测（https://github.com/YuanZo/UIED）
2. **Tesseract OCR** - 文本识别（https://github.com/UB-Mannheim/tesseract）
3. **scikit-image** - SSIM 计算（https://scikit-image.org/）

---

## 📝 文档历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| 1.0 | 2025-01-06 | 初版（7 项改进，完整路线图） |
| TBD | TBD | 补充实测数据、调整权重 |

---

**Last Updated**: 2025-01-06  
**Status**: Draft - 等待初步实现和测试反馈
