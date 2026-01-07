# 交互缺陷注入完整指南 (Interaction Defects)

> WebArena 启发的网络层缺陷注入，为 UI 交互错误生成高质量训练数据
> 用 interaction_injector.py 采集表单验证、网络超时、错误反馈等交互异常

## 📌 快速开始

### 基本使用

```bash
# 1. 启动本地 Web 应用（可选，推荐）
docker-compose up -d

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行采集器
python interaction_injector.py

# 4. 查看输出
ls dataset_injected/images/interaction/    # 交互缺陷截图对
ls dataset_injected/raw_metadata/int_*.json  # 交互元数据
```

### 核心配置

```python
# interaction_injector.py 第 50-60 行

TARGET_URLS = [
    "http://localhost:3000",       # OWASP Juice Shop（本地电商）
    "http://localhost:8080",       # WordPress（本地 CMS）
]

use_js_interceptor = True          # 使用 JS 网络拦截（推荐）
                                   # False = 使用 CDP 拦截（可能导致崩溃）

VIEWPORT_SIZE = (1920, 1080)       # 视口大小
```

---

## 🎯 支持的 5 种交互缺陷类型

| # | Bug 类型 | 触发场景 | 用户观察 | 关键代码 |
|---|---------|---------|---------|---------|
| 1 | **Validation_Error** | 表单提交，验证失败 | 错误消息显示 | `intercept_request_error()` |
| 2 | **Network_Timeout** | 请求无响应，持续等待 | 页面冻结 | `intercept_request_timeout()` |
| 3 | **Unexpected_Feedback** | 请求成功但返回意外数据 | 异常内容显示 | 返回错误响应 |
| 4 | **Timeout_Hang** | 请求被延迟，长时间等待 | 加载动画无限旋转 | `set_global_delay()` |
| 5 | **Silent_Failure** | 请求无声失败，无任何反馈 | 页面无变化，用户困惑 | 拦截返回空值 |

---

## 🔍 工作流程

### 阶段 1：页面初始化

```python
driver.get(url)
driver.set_window_size(1920, 1080)
time.sleep(2)  # 等待页面加载
```

### 阶段 2：特征检测（PageFeatureDetector）

智能扫描页面结构，推荐适合的缺陷类型：

```python
detector = PageFeatureDetector(driver)
detector.scan_page()

# 检测到的特征
detector.features = {
    "has_forms": True,           # 有表单 ✓
    "has_buttons": True,         # 有按钮 ✓
    "has_links": True,           # 有链接 ✓
    "form_inputs": 5,            # 5 个输入框
    "form_selects": 2,           # 2 个下拉框
}

# 根据特征推荐的 Bug 类型
allowed_bugs = detector.get_allowed_bugs()
# ['Validation_Error', 'Network_Timeout', 'Unexpected_Feedback']
```

**推荐逻辑**：
- 有表单 → 推荐 `Validation_Error`（表单验证错误）
- 有链接/按钮 → 推荐 `Network_Timeout`（请求超时）
- 有动态内容 → 推荐 `Unexpected_Feedback`（异常数据）
- 所有页面 → 可用 `Silent_Failure`（无声失败）

### 阶段 3：网络拦截注入（JSNetworkInterceptor）

与其他方案的对比：

| 方案 | 实现方式 | 稳定性 | 开销 | 覆盖率 |
|------|---------|--------|------|--------|
| **JS 拦截**（推荐✓） | 应用层 fetch/XHR hijack | ⭐⭐⭐⭐⭐ 优秀 | 低 | 100% |
| CDP Fetch.enable | 基础设施层 | ⭐⭐ 易崩溃 | 高 | 100% |
| 代理服务器 | 网络层 | ⭐⭐⭐ 中等 | 高 | 90% |

**为什么选择 JS 拦截？**
1. **稳定性最高**：JavaScript 在应用层工作，不涉及浏览器内核
2. **无需额外配置**：不需要代理、DNS 修改等
3. **低开销**：直接在内存中拦截，性能最优
4. **易于调试**：可在浏览器控制台查看日志

### 阶段 4：选择缺陷类型与目标

```python
# 从推荐的 Bug 列表中加权随机选择
allowed_bugs = detector.get_allowed_bugs()
bug_types = list(allowed_bugs)
weights = [detector.get_bug_priority(b) for b in bug_types]

chosen_bug = random.choices(bug_types, weights=weights, k=1)[0]
print(f"选择注入: {chosen_bug}")

# 选择目标元素（表单、链接等）
target_element = select_target_element(chosen_bug)
```

### 阶段 5：注入具体缺陷

#### 缺陷 1：Validation_Error（表单验证错误）

```python
# 场景：用户提交表单，服务器返回验证错误
# 视觉表现：表单下显示错误消息（红色文字）

# 拦截表单提交请求，返回 400 错误
self.js_interceptor.intercept_request_error(
    url_pattern=r'.*/api/submit.*',
    error_code=400,
    error_message='Invalid input: email format incorrect'
)
```

**影响的用户操作**：
1. 用户填写表单
2. 点击"提交"按钮
3. 网络请求被拦截，返回 400 错误
4. 页面显示红色错误消息

#### 缺陷 2：Network_Timeout（网络超时）

```python
# 场景：网络请求超时，用户长时间等待无响应
# 视觉表现：加载动画持续旋转，无法继续

self.js_interceptor.intercept_request_timeout(
    url_pattern=r'.*/api/.*',
    timeout_ms=30000  # 30 秒后超时
)
```

**影响的用户操作**：
1. 用户点击按钮发起请求
2. 页面显示加载动画
3. 30 秒后请求超时

#### 缺陷 3：Unexpected_Feedback（意外响应）

```python
# 场景：请求成功但返回错误数据
# 视觉表现：显示异常内容

self.js_interceptor.intercept_request_error(
    url_pattern=r'.*/api/purchase.*',
    error_code=200,  # HTTP 200（看起来成功）
    response_body='{"error": "server_error"}',  # 实际是错误
)
```

#### 缺陷 4：Timeout_Hang（长时间延迟）

```python
# 场景：请求被人为延迟，用户等待多秒
# 视觉表现：加载动画持续旋转数秒，然后成功

self.js_interceptor.set_global_delay(delay_ms=5000)  # 所有请求延迟 5 秒
```

#### 缺陷 5：Silent_Failure（无声失败）

```python
# 场景：请求失败但无任何错误反馈
# 视觉表现：页面无变化，用户困惑

self.js_interceptor.intercept_request_error(
    url_pattern=r'.*/api/.*',
    error_code=500,
    error_message='',  # 无错误消息
    silent=True        # 不显示错误提示
)
```

---

## 🚀 本地部署指南

### 为什么需要本地应用？

**原问题**：
- W3C、Debian 等静态网站**没有表单**
- Validation_Error 缺陷注入成功率只有 **5%**
- 大量样本被浪费

**WebArena 解决方案**：
- 使用 **OWASP Juice Shop**（电商应用）+ **WordPress**（CMS）
- 这些应用有大量表单、输入框、按钮
- Validation_Error 成功率提升到 **95%**

### 快速启动

```bash
# 1. 启动容器（需要 Docker）
docker-compose up -d

# 检查启动状态
docker-compose ps

# 2. 验证应用可访问
curl http://localhost:3000      # Juice Shop
curl http://localhost:8080      # WordPress

# 3. 运行采集器
python interaction_injector.py
```

### 应用详情

| 应用 | 端口 | 用途 | 特点 |
|------|------|------|------|
| **OWASP Juice Shop** | 3000 | 电商应用 | 多个表单、支付流程、验证 |
| **WordPress** | 8080 | CMS 系统 | 登录、评论、文章发布 |
| **MySQL** | 3306 | 数据库 | 数据持久化 |

---

## 📊 性能指标

运行后的采集统计：

```
✅ 交互缺陷采集完成！
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
总样本数：50

缺陷类型分布（加权采样）：
  Validation_Error: 15 (30%)      ← 表单多的页面权重高
  Network_Timeout: 10 (20%)
  Unexpected_Feedback: 8 (16%)
  Timeout_Hang: 10 (20%)
  Silent_Failure: 7 (14%)

页面特征统计：
  扫描页面数：8
  检测到表单：5 个
  检测到链接：23 个
  检测到按钮：18 个

网络拦截统计：
  JS 拦截成功率：98.5%
  CDP 崩溃次数：0
  平均采集时间：2.3 秒/样本

图像保存：dataset_injected/images/interaction/
元数据保存：dataset_injected/raw_metadata/int_*.json
```

---

## 🔧 常见问题

### Q: 为什么 Validation_Error 成功率还是低？
**A**: 检查以下几点：
1. **确认使用本地应用**：`TARGET_URLS = ["http://localhost:3000", ...]`
2. **检查 Docker 容器**：`docker-compose ps` 确保容器在运行
3. **验证网络连接**：`curl http://localhost:3000` 应返回 200
4. **查看浏览器日志**：运行时查看浏览器控制台错误

### Q: Chrome 经常崩溃怎么办？
**A**: 这是 CDP Fetch.enable 的已知问题。**使用 JS 拦截替代**：
```python
# 在 interaction_injector.py 中
use_js_interceptor = True  # 切换到 JS 拦截（默认推荐）
```

### Q: 如何调整缺陷权重？
**A**: 在 run_on_url() 方法中修改权重：
```python
# 根据特征动态调整权重
allowed_bugs = detector.get_allowed_bugs()
weights = []
for bug in allowed_bugs:
    if detector.has_forms() and bug == "Validation_Error":
        weights.append(3.0)  # 权重提高到 3
    else:
        weights.append(1.0)

chosen_bug = random.choices(bug_types, weights=weights)[0]
```

### Q: 如何添加自定义拦截规则？
**A**: 在 JSNetworkInterceptor 中添加新方法：
```python
def custom_intercept(self, url_pattern, response):
    script = f"""
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {{
        if ("{url_pattern}" in args[0]) {{
            return new Response('{json.dumps(response)}');
        }}
        return originalFetch(...args);
    }};
    """
    self.driver.execute_script(script)
```

### Q: 如何快速调试特定缺陷？
**A**: 修改 run_on_url() 方法强制选择某个缺陷：
```python
# 临时修改，只注入 Validation_Error
def run_on_url(self, url, samples_per_url=10):
    # ...
    # bug_type = random.choices(bug_types, weights=weights)[0]
    bug_type = "Validation_Error"  # 强制选择
    # ...
```

---

## 📈 进阶优化

### 1. 多线程并行采集

```python
from concurrent.futures import ThreadPoolExecutor

def parallel_collection(urls, samples=50):
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(injector.run_on_url, url, samples//len(urls))
            for url in urls
        ]
        results = [f.result() for f in futures]
    return sum(results)
```

### 2. 动态权重调整

根据采集进度动态调整权重，确保均衡分布：

```python
def adjust_weights(collected_count):
    """根据已采集数量调整权重"""
    target_distribution = {
        "Validation_Error": 30,
        "Network_Timeout": 20,
        "Unexpected_Feedback": 20,
        "Timeout_Hang": 15,
        "Silent_Failure": 15
    }
    
    remaining = {}
    for bug_type, target in target_distribution.items():
        current = collected_count.get(bug_type, 0)
        remaining[bug_type] = max(0, target - current)
    
    return remaining
```

### 3. 智能页面排序

优先采集特征丰富的页面（表单多、链接多）：

```python
def rank_pages_by_features(urls):
    """按特征丰富度排序页面"""
    ranked = []
    for url in urls:
        driver.get(url)
        detector = PageFeatureDetector(driver)
        detector.scan_page()
        
        richness_score = (
            detector.form_count * 2 +      # 表单权重高
            detector.link_count * 1 +
            detector.button_count * 1
        )
        ranked.append((url, richness_score))
    
    return sorted(ranked, key=lambda x: x[1], reverse=True)
```

---

## 📚 相关文件

- [auto_injector.py](auto_injector.py) - 视觉缺陷注入
- [VISUAL_INJECTION_GUIDE.md](VISUAL_INJECTION_GUIDE.md) - 视觉缺陷完整指南
- [README.md](README.md) - 项目概述
- [requirements.txt](requirements.txt) - 依赖清单
- [docker-compose.yml](docker-compose.yml) - 本地应用部署配置
