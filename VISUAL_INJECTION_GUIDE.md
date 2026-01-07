# 视觉缺陷注入完整指南 (Visual Defects)

> 自动化 UI 缺陷注入，生成配对的 normal/buggy 图像集合
> 用 auto_injector.py 为 MLLM 视觉理解训练生成高质量数据

## 📌 快速开始

### 基本使用

```bash
# 1. 安装依赖
pip install selenium pillow webdriver-manager

# 2. 运行采集器
python auto_injector.py

# 3. 查看输出
ls dataset_injected/images/visual/       # 截图对（normal + buggy）
ls dataset_injected/raw_metadata/vis_*.json  # 元数据
```

### 核心配置

```python
# auto_injector.py 第 23-50 行

DEBUG_MODE = True
# True  = 调试模式：红框标记缺陷位置，保留所有样本（肉眼检查）
# False = 生产模式：无标记，自动过滤低质量（RMS < 2.0）

VIEWPORT_SIZE = (1920, 1080)
# 视口大小，影响元素候选和布局

TARGET_URLS = [
    "https://www.w3.org/",           # 稳定文档站
    "https://docs.python.org/3/",    # 标准 HTML 结构
    "https://www.debian.org/",       # 极简 HTML
    # ...更多 URL
]
# 建议：选择"长期稳定"的网站（文档、Wiki、门户），避免商业网站（频繁变更）
```

---

## 🎯 支持的 9 种视觉缺陷类型

| # | Bug 类型 | 实现方式 | 视觉特征 | 难度 |
|---|---------|---------|---------|------|
| 1 | **Layout_Overlap** | CSS `transform: translate()` | 元素与周围内容重叠 | ⭐ 低 |
| 2 | **Element_Missing** | CSS `visibility: hidden` | 元素消失，留下空白 | ⭐ 低 |
| 3 | **Text_Overflow** | 文本注入长字符串 | 文本超出容器边界 | ⭐ 低 |
| 4 | **Broken_Image** | `img.src = "invalid"` | 图片无法加载 | ⭐ 低 |
| 5 | **Layout_Alignment** | CSS `text-align` 变更 | 对齐错误（左→右等） | ⭐⭐ 中 |
| 6 | **Layout_Spacing** | margin/padding 修改 | 间距不一致 | ⭐⭐ 中 |
| 7 | **Data_Format_Error** | 替换数字/日期格式 | 显示格式异常 | ⭐⭐ 中 |
| 8 | **Style_Color_Contrast** | 背景色改为相似色 | 对比度不足，看不清 | ⭐⭐ 中 |
| 9 | **Style_Size_Inconsistent** | font-size/width 修改 | 尺寸不一致 | ⭐⭐⭐ 高 |

---

## 🔍 工作流程

### 1. 初始化（__init__）
- 启动 Selenium WebDriver（Chrome）
- 设置视口大小（1920×1080）
- 创建输出目录结构

### 2. 访问页面（_visit_url）
```python
driver.get(url)
driver.set_window_size(1920, 1080)
time.sleep(3)  # 等待加载完成
```

### 3. 采集正常截图（_capture_normal）
```python
# 保存当前页面截图作为基准
screenshot = driver.get_screenshot_as_png()
save_image("normal.png")
```

### 4. 候选元素选择（get_candidate_elements）
- 递归遍历 DOM 树
- 过滤条件：
  - 可见性：visibility + opacity > 0
  - 大小：min(width, height) ≥ 20px
  - 类型：排除 script, style, meta 等
- 返回：所有符合条件的 WebElement

### 5. 随机选择 Bug 类型
```python
bug_type = random.choice(BUG_TYPES)  # 从 9 种中随机选一个
element = random.choice(candidate_elements)
```

### 6. 注入缺陷（inject_bug）
根据 bug_type 执行不同的 JavaScript 修改

**示例：Layout_Overlap**
```python
script = f"""
    arguments[0].style.transform = 'translate({offset_x}px, {offset_y}px)';
"""
driver.execute_script(script, element)
```

### 7. 采集缺陷截图（_capture_buggy）
```python
screenshot = driver.get_screenshot_as_png()
save_image("buggy.png")
```

### 8. 质量验证（_validate_sample）

使用多维指标确保数据质量：

| 指标 | 计算方法 | 阈值 | 说明 |
|------|---------|------|------|
| **RMS** | 像素均方根差异 | > 2.0 | 像素变化程度 |
| **SSIM** | 结构相似度 | < 0.95 | 避免过度相似 |
| **直方图差异** | 颜色分布 KL 散度 | > 0.1 | 颜色变化明显 |
| **边缘差异** | Canny 边缘差异 | > 5% | 布局变化检测 |

**过滤规则**（生产模式）：
```python
if rms < 2.0 or ssim > 0.95:
    # 丢弃低质量样本
    return False
```

### 9. 生成元数据（_generate_metadata）
```json
{
  "id": "vis_a1b2c3d4",
  "url": "https://www.w3.org/",
  "bug_type": "Layout_Overlap",
  "element_xpath": "//div[@class='content']",
  "modification": {
    "property": "transform",
    "from": "translate(0px, 0px)",
    "to": "translate(50px, 40px)"
  },
  "metrics": {
    "rms": 15.3,
    "ssim": 0.82,
    "histogram_kl": 0.35,
    "edge_diff": 8.5
  },
  "timestamp": "2025-01-07T10:30:45Z"
}
```

### 10. 还原页面（_restore_element）
- 移除注入的修改
- 恢复元素原始样式
- 准备下一轮采集

---

## 📊 数据统计

运行后输出示例：

```
✅ 采集完成！
━━━━━━━━━━━━━━━━━━━━━━━━
总样本数：50
  Layout_Overlap: 6 (12%)
  Element_Missing: 4 (8%)
  Text_Overflow: 8 (16%)
  Broken_Image: 5 (10%)
  Layout_Alignment: 6 (12%)
  Layout_Spacing: 7 (14%)
  Data_Format_Error: 4 (8%)
  Style_Color_Contrast: 2 (4%)
  Style_Size_Inconsistent: 8 (16%)

验证统计：
  RMS (平均): 12.5 ± 3.2
  SSIM (平均): 0.78 ± 0.08
  直方图差异 (平均): 0.28 ± 0.12
  
图像保存：dataset_injected/images/visual/
元数据保存：dataset_injected/raw_metadata/vis_*.json
```

---

## 🔧 常见问题

### Q: 为什么某些网站采集失败？
**A**: 常见原因：
1. **JavaScript 防护**：网站使用 CSP，阻止脚本注入
   - 解决：选择 W3C、Debian、Python 文档这类开放网站
2. **动态加载**：内容通过 AJAX 异步加载，等待时间不足
   - 解决：增加 `time.sleep()` 等待时间
3. **反爬虫**：网站检测到自动化访问
   - 解决：添加 User-Agent 头、延迟请求

### Q: 如何调整采样分布？
**A**: 修改 auto_injector.py 中的采样权重：
```python
# 第 ~600 行
bug_weights = {
    "Layout_Overlap": 1,
    "Element_Missing": 1,
    "Text_Overflow": 2,            # 权重 2（采样概率翻倍）
    "Broken_Image": 1,
    "Layout_Alignment": 1,
    "Layout_Spacing": 1,
    "Data_Format_Error": 1,
    "Style_Color_Contrast": 1,
    "Style_Size_Inconsistent": 2,  # 权重 2
}
```

### Q: 如何添加新的 bug 类型？
**A**: 在 `inject_bug()` 方法中添加新分支：
```python
def inject_bug(self, element, bug_type):
    # ...
    elif bug_type == "Custom_Bug":
        script = """
            arguments[0].style.customProperty = 'customValue';
        """
        self.driver.execute_script(script, element)
```

### Q: 如何在 DEBUG_MODE 下快速检查效果？
**A**: 
1. 设置 `DEBUG_MODE = True`
2. 修改 TARGET_URLS 为单个 URL
3. 修改循环次数为 5
4. 运行 `python auto_injector.py`
5. 检查输出图片，红框标记会显示缺陷位置

---

## 📈 性能优化建议

| 优化项 | 方法 | 效果 |
|--------|------|------|
| **加速截图** | 禁用图片加载 | -30% 时间 |
| **并行采集** | 多进程 | 4x 吞吐 |
| **缓存元素** | 一次加载多个样本 | -50% I/O |
| **智能采样** | 根据元素尺寸调整参数 | 更高成功率 |

---

## 📚 相关文件

- [interaction_injector.py](interaction_injector.py) - 交互缺陷注入
- [INTERACTION_INJECTION_GUIDE.md](INTERACTION_INJECTION_GUIDE.md) - 交互缺陷完整指南
- [templates.py](templates.py) - 自然语言报告生成
- [README.md](README.md) - 项目概述
