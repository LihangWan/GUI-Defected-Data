# WebArena-Inspired Data Injection Framework

## 概览

本项目改进了原始的数据注入框架，采用 **WebArena (ICLR 2024)** 的思想：不在静态文档上进行错误注入，而是在真实的、可交互的 Web 应用上执行。

### 核心改进

1. **本地自托管 Web 应用**：放弃爬 GitHub/W3C（静态文档），改为本地部署 OWASP Juice Shop 和 WordPress
2. **动态特征检测**：`feature_detector.py` 扫描页面元素，动态决定可注入的 Bug 类型
3. **JavaScript 网络拦截**：`js_network_injector.py` 替代不稳定的 CDP Fetch.enable
4. **视觉反馈增强**：为交互错误添加可视化指示（点击特效、无响应标记等）

---

## 快速开始

### 前置要求

- Docker & Docker Compose
- Python 3.8+
- Chrome 浏览器
- Selenium WebDriver

### Step 1: 启动本地 Web 应用

```bash
docker-compose up -d
```

这会启动：
- **OWASP Juice Shop** (电商应用): http://localhost:3000
- **WordPress** (CMS): http://localhost:8080

等待应用完全启动（约 30-60 秒）：

```bash
docker-compose logs -f juice-shop  # 查看 Juice Shop 日志
```

### Step 2: 安装依赖

```bash
pip install selenium webdriver-manager pillow
```

### Step 3: 运行数据采集

#### 示例 1：采集视觉类错误

```python
from auto_injector import AutoInjector

injector = AutoInjector()

# 目标 URL 替换为本地应用
injector.TARGET_URLS = [
    "http://localhost:3000",      # Juice Shop
    "http://localhost:8080",       # WordPress
]

injector.run(num_samples=100)
```

#### 示例 2：采集交互类错误

```python
from interaction_injector import InteractionInjector
from feature_detector import FeatureDetector
from js_network_injector import JSNetworkInjector

injector = InteractionInjector()
injector.TARGET_URLS = [
    "http://localhost:3000",
    "http://localhost:8080",
]

injector.run(num_samples=100)
```

---

## 模块详解

### 1. `feature_detector.py` - 页面特征检测

自动扫描页面结构，推断页面类型和可注入的 Bug 类型。

**使用示例：**

```python
from feature_detector import FeatureDetector
from selenium import webdriver

driver = webdriver.Chrome()
driver.get("http://localhost:3000")

detector = FeatureDetector(driver)
features = detector.scan_page()

print(features["page_type"])  # 输出: 'ecommerce'
print(detector.get_allowed_bugs())  # 输出: ['Navigation_Error', 'Validation_Error', ...]
print(detector.get_bug_priority())  # 输出: 权重字典

detector.print_summary()  # 打印格式化总结
```

**页面类型推断：**

| 页面类型 | 特征 | 推荐 Bug |
|---------|------|---------|
| `static` | 无表单，无交互 | Navigation_Error, Timeout_Hang |
| `form_heavy` | 3+ 个表单或 10+ 输入框 | Validation_Error, Unexpected_Task_Result, Silent_Failure |
| `ecommerce` | 购物车、结账、支付表单 | Validation_Error, Unexpected_Task_Result (重点) |
| `interactive` | 1-2 个表单，5+ 按钮 | Operation_No_Response, Timeout_Hang |

---

### 2. `js_network_injector.py` - JavaScript 网络拦截

通过注入 JavaScript 代码来拦截 `fetch` 和 `XMLHttpRequest`，模拟网络故障。

**优势：**
- ✅ 比 CDP 稳定（应用层 vs 驱动层）
- ✅ 精确控制（按 URL 模式拦截）
- ✅ 无 DevTools 开销

**使用示例：**

```python
from js_network_injector import JSNetworkInjector
from selenium import webdriver

driver = webdriver.Chrome()

# 注入拦截器（必须在页面加载前）
interceptor = JSNetworkInjector(driver)
driver.get("http://localhost:3000")
interceptor.inject_fetch_interceptor()

# 模拟特定 URL 的超时
interceptor.intercept_request_timeout(r'api/payment.*')

# 模拟特定 URL 的 HTTP 500 错误
interceptor.intercept_request_error(r'api/checkout', error_code=500)

# 模拟全局延迟（所有请求延迟 2 秒）
interceptor.set_global_delay(2000)

# 获取拦截日志
logs = interceptor.get_logs()
for log in logs:
    print(f"[{log['type']}] {log['url']}")

# 关闭拦截器
interceptor.disable_interceptor()

# 重置状态
interceptor.reset()
```

---

### 3. `auto_injector.py` (改进版) - 视觉类错误采集

现在集成了 `FeatureDetector`，可以智能地选择注入的 Bug 类型。

**关键改进：**

```python
from auto_injector import AutoInjector
from feature_detector import FeatureDetector

class ImprovedAutoInjector(AutoInjector):
    def should_inject_bug(self, driver, bug_type):
        """检查页面是否支持此 Bug 注入"""
        detector = FeatureDetector(driver)
        detector.scan_page()
        allowed_bugs = detector.get_allowed_bugs()
        
        return bug_type in allowed_bugs
```

---

### 4. `interaction_injector.py` (改进版) - 交互类错误采集

现在使用 JS 网络拦截代替 CDP。

**关键改进：**

```python
from interaction_injector import InteractionInjector
from js_network_injector import JSNetworkInjector

class ImprovedInteractionInjector(InteractionInjector):
    def inject_timeout(self, driver, url_pattern):
        """模拟网络超时"""
        interceptor = JSNetworkInjector(driver)
        interceptor.inject_fetch_interceptor()
        interceptor.intercept_request_timeout(url_pattern)
        
    def inject_http_error(self, driver, url_pattern, error_code=500):
        """模拟 HTTP 错误"""
        interceptor = JSNetworkInjector(driver)
        interceptor.inject_fetch_interceptor()
        interceptor.intercept_request_error(url_pattern, error_code)
```

---

## 最佳实践

### ✅ 采集流程

1. **环境感知**：先用 `FeatureDetector` 扫描页面
2. **智能选择**：根据 `get_allowed_bugs()` 决定注入什么
3. **权重平衡**：使用 `get_bug_priority()` 调整采样比例
4. **视觉验证**：保留截图证据（Before/After）
5. **元数据记录**：保存页面特征、URL、Bug 类型等

### ❌ 避免的错误

| ❌ 错误做法 | ✅ 正确做法 |
|-----------|---------|
| 在"静态页面"注入 Validation_Error | 先扫描，确认有表单再注入 |
| 用 CDP Fetch.enable 拦截所有流量 | 用 JS 只拦截关键请求 |
| 盲目均匀分布 Bug 类型 | 根据页面特征调整权重 |
| 无视觉反馈的交互错误 | 添加点击特效、无响应标记 |

---

## 数据集输出结构

```
dataset_injected/
├── images/
│   ├── visual/              # 视觉类错误图片
│   │   ├── layout_overlap_xxx.png
│   │   ├── element_missing_xxx.png
│   │   └── ...
│   └── interaction/         # 交互类错误图片
│       ├── timeout_xxx.png
│       ├── http_error_xxx.png
│       └── ...
├── labels/                  # 标签文件
│   ├── visual_xxx.json
│   ├── interaction_xxx.json
│   └── ...
├── raw_metadata/            # 原始元数据
│   ├── vis_*.json          # 视觉类元数据
│   ├── int_*.json          # 交互类元数据
│   └── ...
└── training_data/
    └── train_sft.jsonl     # SFT 训练数据（自然语言 + 图像对）
```

---

## 故障排除

### 问题 1: Docker 容器无法启动

```bash
# 查看日志
docker-compose logs juice-shop

# 检查端口占用
netstat -an | grep 3000

# 清理并重启
docker-compose down -v
docker-compose up -d
```

### 问题 2: Feature Detector 返回 "unknown" 页面类型

页面可能太复杂或结构非常规。你可以手动添加特征检测逻辑：

```python
detector = FeatureDetector(driver)
features = detector.scan_page()

# 打印原始特征，手动调整
print(json.dumps(features, indent=2))

# 修改 _infer_page_type 方法
```

### 问题 3: JS 网络拦截不工作

确保在页面加载前注入拦截器：

```python
interceptor = JSNetworkInjector(driver)
driver.get("http://localhost:3000")
success = interceptor.inject_fetch_interceptor()
print(f"Injection: {success}")  # 应该打印 True
```

### 问题 4: 视觉错误在截图中不明显

- 增加 DEBUG_MODE = True，查看是否有红框标记
- 检查截图对比（Before vs After）
- 确认 PIL 正确裁剪和突出显示区域

---

## 配置参数

在各脚本中修改这些参数来调整行为：

### `auto_injector.py`

```python
DEBUG_MODE = True              # 调试模式（显示红框）
OUTPUT_DIR = "dataset_injected"
VIEWPORT_SIZE = (1920, 1080)
TARGET_URLS = [...]            # 本地 URL
```

### `interaction_injector.py`

```python
TIMEOUT_DURATION = 15000       # 超时时长（毫秒）
ERROR_CODES = [500, 503, 504]  # HTTP 错误码
RETRY_ATTEMPTS = 3
```

### `feature_detector.py`

```python
# 修改 _infer_page_type() 的阈值
form_count >= 3          # 判定为 form_heavy
input_count >= 10
```

---

## 引用

- **WebArena**: [Browser-based Environment for Autonomous Agents](https://webarena.dev/)
- **OWASP Juice Shop**: [Intentionally Insecure Web Application](https://owasp.org/www-project-juice-shop/)
- **Selenium WebDriver**: [Browser Automation Framework](https://www.selenium.dev/)

---

## 许可证

MIT License

