# UI Bug 自动化数据集生成系统

> 基于 Selenium + WebArena 的缺陷注入框架  
> 为 MLLM 视觉理解与交互错误检测生成高质量训练数据

---

## 🆕 **最新更新** (2026-01)

- 交互类缺陷注入切换到 `interaction_engine/`（入口 `main_interaction.py`），新增原生优先策略与多样化兜底样式。
- 新增交互数据指南：[INTERACTION_BUG_DATA_GUIDE.md](INTERACTION_BUG_DATA_GUIDE.md)

---

## 📌 快速导航

### 🎯 按使用场景选择

| 场景 | 文档 | 说明 |
|------|------|------|
| **视觉缺陷**（布局错位、颜色对比、文本溢出等） | [auto_injector.py](auto_injector.py) | 视觉缺陷采集脚本（脚本内含说明） |
| **交互缺陷**（Big Three：404/无响应/错误结果） | [INTERACTION_BUG_DATA_GUIDE.md](INTERACTION_BUG_DATA_GUIDE.md) | 交互数据类型、生成流程与质量策略 |
| **交互系统快速验证** | [verify_bugs.py](verify_bugs.py) | 交互注入回归验证脚本 |

---

## 📦 核心功能

### 视觉缺陷注入（auto_injector.py）

采集**配对截图**（normal + buggy），用于训练视觉缺陷检测模型。

```bash
python auto_injector.py
```

**支持 9 种缺陷类型**：
- 低难度：Layout_Overlap, Element_Missing, Text_Overflow, Broken_Image
- 中难度：Layout_Alignment, Layout_Spacing, Data_Format_Error, Style_Color_Contrast
- 高难度：Style_Size_Inconsistent

**质量保证**：
- RMS + SSIM + 直方图 + 边缘差异多维验证
- DEBUG 模式下红框标记缺陷位置
- 生产模式自动过滤低质量样本

### 交互缺陷注入（main_interaction.py）

采集**交互异常**（Navigation_Error、Operation_No_Response、Unexpected_Task_Result），用于训练交互错误检测。

```bash
python main_interaction.py
```

**支持 3 类核心缺陷（Big Three）**：
1. **Navigation_Error** - 错误路由/404/跳转异常
2. **Operation_No_Response** - 点击无响应/长时间卡顿
3. **Unexpected_Task_Result** - 错误提示或结果异常（toast/snackbar）

**技术亮点**：
- ✅ 原生优先：优先使用站点原生 404/loading/toast 组件，避免模板过拟合
- ✅ 多样化兜底：`interaction_engine/visual_styles.py` 提供 5 组多样化样式
- ✅ 质量验证：注入后进行可见性/可交互性/视觉变化验证
- ✅ 可扩展：站点列表与采样参数在 `interaction_engine/config.py` 配置

---

## 🚀 快速开始

### 1️⃣ 安装依赖

```bash
pip install -r requirements.txt
```

**依赖清单**：
- selenium >= 4.0
- pillow >= 9.0
- webdriver-manager
- (可选) docker + docker-compose

### 2️⃣ 采集视觉缺陷（公开网站）

不需要本地部署，直接从公开网站采集：

```bash
python auto_injector.py
```

配置 `auto_injector.py` 中的 TARGET_URLS 选择目标网站。

**推荐网站**：
- https://www.w3.org/
- https://docs.python.org/3/
- https://www.debian.org/
- https://en.wikipedia.org/

输出：`dataset_injected/images/visual/` + `raw_metadata/vis_*.json`

### 3️⃣ 采集交互缺陷（需本地应用）

#### 步骤 A：启动本地应用（Docker）

```bash
# 安装 Docker Desktop (https://www.docker.com/products/docker-desktop)

# 启动容器
docker-compose up -d

# 验证启动
docker-compose ps
curl http://localhost:3000      # OWASP Juice Shop
curl http://localhost:8080      # WordPress
```

#### 步骤 B：运行采集器

```bash
python main_interaction.py
```

输出：`dataset_injected/images/interaction/` + `raw_metadata/int_*.json`

---

## 📊 数据生成

- 交互类数据生成与质量策略详见 [INTERACTION_BUG_DATA_GUIDE.md](INTERACTION_BUG_DATA_GUIDE.md)

## 📊 数据输出格式

### 视觉缺陷输出

```
dataset_injected/
├── images/visual/
│   ├── vis_abc123_normal.png     # 正常截图
│   ├── vis_abc123_buggy.png      # 缺陷截图
│   └── ...
├── raw_metadata/
│   ├── vis_abc123.json           # 元数据
│   └── ...
└── training_data/
    └── train_sft.jsonl           # 自然语言报告（可选）
```

### 交互缺陷输出

```
dataset_injected/
├── images/interaction/
│   ├── int_abc123_action.png     # 触发前截图
│   ├── int_abc123_end.png        # 缺陷后截图
│   └── ...
└── raw_metadata/
    ├── int_abc123.json           # 元数据
    └── ...
```

---

## ⚙️ 核心配置

### 视觉缺陷（auto_injector.py）

```python
DEBUG_MODE = True
# True  = 红框标记，保留所有样本
# False = 无标记，自动过滤低质量（RMS < 2.0）

TARGET_URLS = [
    "https://www.w3.org/",
    "https://docs.python.org/3/",
]
```

### 交互缺陷（interaction_injector.py）

```python
TARGET_URLS = [
    "http://localhost:3000",    # OWASP Juice Shop
    "http://localhost:8080",    # WordPress
]

use_js_interceptor = True       # 使用 JS 拦截（推荐）
```

---

## 🔧 常见问题

**Q: 如何选择视觉还是交互缺陷？**

取决于训练任务：
- 视觉缺陷检测 → 视觉缺陷（需要正常/缺陷截图对）
- 交互错误检测 → 交互缺陷（需要表单验证、网络超时等）
- 端到端理解 → 两者都用

**Q: 为什么交互缺陷需要本地应用？**

两大原因：
1. 静态网站（W3C、Debian）没有表单，Validation_Error 成功率只有 5%
2. 本地应用可以精确控制网络行为，注入稳定可重复

**Q: Chrome 崩溃怎么办？**

使用 JS 拦截替代 CDP（后者易崩溃）：
```python
use_js_interceptor = True  # ✅ 推荐
```

---

## 📚 文档导航

```
.
├── README.md                        # 项目总览（本文件）
├── INTERACTION_BUG_DATA_GUIDE.md    # 交互缺陷数据指南
│
├── auto_injector.py                 # 视觉缺陷采集脚本
├── main_interaction.py              # 交互缺陷采集入口
├── templates.py                     # 自然语言报告生成
│
├── docker-compose.yml               # 本地应用部署
├── requirements.txt                 # 依赖清单
└── dataset_injected/                # 输出数据
    ├── images/
    │   ├── visual/
    │   └── interaction/
    └── raw_metadata/
```

---

## 📈 性能指标

| 指标 | 目标 | 说明 |
|------|------|------|
| **视觉采集速度** | 10 样本/分钟 | 无重型 JavaScript |
| **样本质量** | RMS > 2.0 | 像素差异明显 |
| **交互成功率** | 95% | WebArena 本地应用 |
| **浏览器稳定性** | 0% 崩溃 | JS 拦截（无 CDP） |

---

## 🎓 学术背景

### 参考论文

1. **WebArena** (ICLR 2024)
   - 本地部署应用替代公开网站
   
2. **DCGen** (arxiv 2024)
   - MLLM 失败分布：遗漏 85%、错位 12.7%、失真 2.6%

### 技术创新

- 应用层网络拦截替代不稳定的 CDP
- 页面特征自动检测与推荐
- 动态加权采样确保分布均衡
- 多维质量验证（RMS + SSIM + 直方图 + 边缘）

---

## 🎯 使用建议

### 快速验证（5 分钟）
```bash
python auto_injector.py  # 修改 SAMPLES_PER_URL=1
ls dataset_injected/images/visual/
```

### 生成训练集（1 小时）
```bash
python auto_injector.py
docker-compose up -d
python main_interaction.py
python templates.py generate
```

### 生产级收集（8 小时+）
```bash
# 配置多个 URL、增加采样、使用多进程
```

---

## 📄 License

MIT License - 学术研究与教学用途

---

**版本**：v3.0（集成 WebArena 改进）  
**更新时间**：2025-01-07

