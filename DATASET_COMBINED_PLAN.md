# UI Bug 注入爬虫完整技术方案

> 基于 dev.to 文章《How we built UI bug detection from scratch》对标分析  
> 目标：构建高质量、可迁移的 UI 视觉缺陷检测数据集

---

## 📋 目录

1. [方案概览](#方案概览)
2. [Bug 类型体系](#bug-类型体系)
3. [爬虫架构优化](#爬虫架构优化)
4. [多站点自适应加载](#多站点自适应加载)
5. [质量验证体系](#质量验证体系)
6. [成本收益分析](#成本收益分析)
7. [实施路线图](#实施路线图)
8. [代码实现参考](#代码实现参考)

---

## 🎯 方案概览

### 核心目标

| 维度 | 当前状态 | 目标状态 | 关键指标 |
|------|---------|---------|---------|
| **样本生成速度** | 3s/样本 | 0.5-1s/样本 | 10K 样本 1.5-3h |
| **数据质量** | RMS 过滤 | 多维验证 + 可视化 | 有效样本率 >85% |
| **站点覆盖** | 6 个文档站 | 15+ 多类型站点 | 3 档 × 3 分辨率 |
| **并发能力** | 单线程 | 15 并发 | 加速 5-10 倍 |
| **可重复性** | 中等 | 高（Markdown 校验） | 一致性 >95% |

### 技术栈

```
爬虫层：Selenium + Chrome DevTools Protocol (CDP)
加载优化：资源拦截 + 自适应等待 + 降级策略
并发控制：ThreadPoolExecutor + Driver Pool
质量保证：RMS + SSIM + 直方图 + 边缘差异
数据管理：JSON 元数据 + 图片对 + 验证报告
```

---

## 🐛 Bug 类型体系

```python
✅ 已实现的 Bug 类型：
1. Layout_Overlap       # 布局重叠（元素位置偏移）
2. Element_Missing      # 元素消失（display:none / visibility:hidden）
3. Text_Overflow        # 文本溢出（内容超出容器）
4. Broken_Image         # 图片破损（src 置空/错误）
5. Layout_Alignment     # 布局对齐错误（text-align / vertical-align）
6. Layout_Spacing       # 布局间距不一致（margin / padding 异常）
7. Data_Format_Error    # 数据格式错误（数字/日期显示异常）
8. Style_Color_Contrast # 颜色对比度（前景/背景色对比不足）
9. Style_Size_Inconsistent # 尺寸不一致（font-size / width / height）
```

### 1.2 行业对标（dev.to 文章方案）

| Bug 类型 | 行业方案 | 当前状态 | 优先级 |
|---------|---------|---------|--------|
| **视觉/资源类** |
| Broken Image | ✅ 已有 | ✅ 已实现 | - |
| Missing Content | ⚠️ 部分覆盖 | Element_Missing 覆盖元素，缺文本内容变体 | 中 |
| **布局类** |
| Empty Layout | ❌ 缺失 | **需新增** | 🔴 高 |
| Broken Layout | ⚠️ 部分覆盖 | Layout_Overlap/Spacing 可覆盖 | 低 |
| Overlapping Content | ✅ 已有 | ✅ Layout_Overlap | - |
| **样式类** |
| Letter Spacing Issue | ❌ 缺失 | **需新增** | 🔴 高 |
| Inconsistent Font Size | ✅ 已有 | ✅ Style_Size_Inconsistent | - |
| Inconsistent Color Scheme | ⚠️ 部分覆盖 | Color_Contrast 关注对比度，非一致性 | 🟡 中 |
| Outdated Style | ❌ 不适用 | 难以自动化注入，定义模糊 | 低 |
| **滚动类** |
| Unnecessary Scroll | ❌ 缺失 | **需新增** | 🔴 高 |
| Unnecessary Horizontal Scroll | ❌ 缺失 | **需新增** | 🔴 高 |

### 1.3 新增 Bug 类型详解

#### 🔴 高优先级（立即实现）

**① Empty Layout（布局空白）**

```javascript
// 注入方法 A：隐藏容器内所有子元素
container.style.minHeight = '500px';
container.style.backgroundColor = '#f5f5f5';
Array.from(container.children).forEach(el => {
    el.style.display = 'none';
});

// 注入方法 B：清空内容但保留占位
container.textContent = '';
container.style.height = '300px';
container.style.border = '1px solid #e0e0e0';
```

- **视觉特征**：大面积空白区域，与周围填充内容形成对比
- **真实场景**：API 加载失败、列表为空但未显示占位符
- **易识别度**：✅ 高（大面积空白明显）
- **实现难度**：简单
- **验证阈值**：SSIM diff > 0.25, hist_diff > 800

---

**② Letter Spacing Issue（字间距问题）**

```javascript
const element = document.querySelector('p, h1, h2, span, div');
const spacings = ['-5px', '-2px', '0.5px', '12px', '24px', '40px'];
if (element && element.textContent.trim()) {
    element.style.letterSpacing = spacings[Math.floor(Math.random() * spacings.length)];
    element.setAttribute('data-injected', 'true');
}
```

- **视觉特征**：
  - 过大：`H    e    l    l    o` 字母分散
  - 过小：`Hello` 字母挤压甚至重叠
- **真实场景**：CSS 继承错误、字体渲染异常
- **易识别度**：⚠️ 中等（需文本对比）
- **实现难度**：简单
- **验证阈值**：RMS diff > 1.5, edge_diff > 150

---

**③ Unnecessary Scroll（不必要的滚动）**

```javascript
// 水平溢出（最常见）
const target = document.querySelector('main, .content, body');
target.style.width = `${window.innerWidth + 200}px`;
target.style.overflowX = 'visible';

// 垂直溢出
target.style.height = `${window.innerHeight + 300}px`;
target.style.overflowY = 'visible';

// 或强制 body 出现滚动
document.body.style.width = `${window.innerWidth + 150}px`;
```

- **视觉特征**：右侧或底部出现滚动条，内容被裁剪
- **真实场景**：响应式布局失效、固定宽度溢出
- **易识别度**：✅ 高（滚动条明显）
- **实现难度**：简单
- **验证阈值**：RMS diff > 0.8, SSIM diff > 0.15

---

#### 🟡 中优先级（可选增强）

**④ Inconsistent Color Scheme（配色方案不一致）**

```javascript
const buttons = document.querySelectorAll('button, .btn, a.button');
if (buttons.length > 1) {
    const colors = ['#ff0000', '#00ff00', '#0000ff', '#ff00ff', '#ffff00'];
    buttons.forEach((btn, i) => {
        if (i < 3) {  // 只改部分，形成不一致
            btn.style.backgroundColor = colors[i % colors.length];
            btn.style.color = '#ffffff';
        }
    });
}
```

- **视觉特征**：同类元素颜色风格不统一
- **真实场景**：主题切换不完全、CSS 变量失效
- **易识别度**：✅ 高（色差明显）
- **实现难度**：中等（需识别同类元素）
- **验证阈值**：hist_diff > 1200, SSIM diff > 0.20

---

**⑤ Missing Content（内容缺失 - 细分）**

```javascript
// 变体 1：仅清空文本，保留结构
element.textContent = '';
element.innerText = '';

// 变体 2：移除特定子元素
if (element.firstChild) element.firstChild.remove();

// 变体 3：隐藏列表项
const items = element.querySelectorAll('li, tr, .item');
if (items.length > 2) {
    items[1].style.display = 'none';  // 隐藏中间项
}
```

- **视觉特征**：按钮无文字、标签空白、列表缺项
- **真实场景**：数据绑定失败、国际化字符串缺失
- **易识别度**：✅ 高
- **实现难度**：简单
- **验证阈值**：hist_diff > 600, SSIM diff > 0.18

---

### 1.4 实现建议

#### ✅ 立即增加（2-3 个）
```
优先级排序：
1. Empty Layout     - 高频缺陷，视觉清晰，易验证
2. Letter Spacing   - 独特视觉特征，简单实现
3. Unnecessary Scroll - 明显滚动条，易检测
```

#### ⚠️ 阶段性增加（数据量 >10K 后）
```
4. Inconsistent Color Scheme
5. Missing Content 细分变体
```

#### ❌ 不建议增加
```
- Outdated Style：主观审美，无客观标准
- 过于抽象的"设计不佳"类 bug
```

---

## 🚀 爬虫架构优化
### 2.1 为何当前方案优于行业实践

#### 行业方案（dev.to 文章）遇到的问题

| 问题 | 原因 | 结果 |
|------|------|------|
| **速度慢** | 3s/样本 | 10K 样本需 8+ 小时 |
| **过程脆弱** | 商业网站变更频繁 | 需频繁重试，数据生成不可靠 |
| **Markdown 不一致** | 懒加载、A/B 测试、动态内容 | 无法形成严格配对样本 |

#### 当前方案的优势

| 优势 | 实现方式 | 效果 |
|------|---------|------|
| **站点选择优** | 选择长期稳定的文档/门户/wiki 站点 | 避免 A/B 测试、广告系统干扰 |
| **注入系统化** | 9+3 种 bug 类型，覆盖布局/样式/滚动 | 比简单 style 破坏更全面 |
| **网络可控** | headless + page_load_strategy='eager' | 减少不必要的资源等待 |

#### 推荐站点列表

```python
TARGET_URLS = {
    'fast': [  # 文档类：极度稳定
        "https://www.w3.org/",
        "https://www.apache.org/",
        "https://www.debian.org/",
        "https://docs.python.org/3/",
        "https://en.wikipedia.org/wiki/Main_Page",
    ],
    'medium': [  # 新闻/表单类：相对稳定
        "https://www.bbc.com/",
        "https://www.reuters.com/",
        "https://developer.mozilla.org/",
        "https://stackoverflow.com/",
    ],
    'slow': [  # 电商/社交类：动态内容多
        "https://www.amazon.com/",
        "https://www.ebay.com/",
        "https://github.com/",
    ]
}
```

---

### 2.2 核心提速手段

#### 手段 1：批量注入（Batch Processing）

**当前问题**：每次加载页面只生成 1 对样本
```
1 样本 = load(2s) + 候选(0.3s) + 注入(0.3s) + 截图(0.5s) = 3s
5 样本 = 5 × 3s = 15s
```

**优化方案**：一次加载生成多对样本
```python
def save_multiple_pairs(self, url, samples_per_page=5):
    """从同一页面生成多对样本"""
    self.load_page(url)  # 仅 1 次加载
    
    for _ in range(samples_per_page):
        candidates = self.get_candidate_elements()
        target = random.choice(candidates)
        
        # 1. 正常截图
        normal_path = self._save_screenshot(f"normal_{uuid.uuid4().hex[:8]}")
        
        # 2. 注入 bug
        bug_type = random.choice(self.BUG_TYPES)
        success, info = self.inject_bug(target, bug_type)
        
        if not success:
            continue
        
        # 3. buggy 截图
        buggy_path = self._save_screenshot(f"buggy_{uuid.uuid4().hex[:8]}")
        
        # 4. 验证并保存
        if self._validate_pair(normal_path, buggy_path, bug_type):
            self._save_metadata(url, bug_type, normal_path, buggy_path, info)
        
        # 5. 轻量重置（不 reload）
        self._reset_page_light()
```

**效果**：
```
5 样本 = load(2s) + 5 × [注入+截图+重置](0.8s) = 6s
→ 提速 2.5 倍（15s → 6s）
```

---

#### 手段 2：轻量重置（Lightweight Reset）

**当前问题**：每次注入后完整 reload 页面
```python
self.driver.refresh()  # 2s
self.wait_for_page_ready()  # 1-3s
```

**优化方案**：仅清理注入痕迹，不 reload
```python
def _reset_page_light(self):
    """轻量重置：移除注入标记，恢复初始样式"""
    script = """
    (function() {
        // 移除所有注入的 style 标签
        document.querySelectorAll('[data-injected="true"]').forEach(el => {
            el.remove();
        });
        
        // 恢复所有元素的 inline 样式
        document.querySelectorAll('*').forEach(el => {
            el.style.cssText = '';
        });
        
        // 重新加载被替换的图片
        document.querySelectorAll('img[data-original-src]').forEach(img => {
            img.src = img.getAttribute('data-original-src');
            img.removeAttribute('data-original-src');
        });
        
        // 恢复文本内容
        document.querySelectorAll('[data-original-text]').forEach(el => {
            el.textContent = el.getAttribute('data-original-text');
            el.removeAttribute('data-original-text');
        });
    })();
    """
    self.driver.execute_script(script)
    time.sleep(0.2)  # 短暂等待 DOM 更新
```

**效果**：
```
完整 reload = 2-3s
轻量重置 = 0.2s
→ 提速 10-15 倍
```

---

#### 手段 3：浏览器池（Browser Pooling）

**当前问题**：每个 URL 都创建新 driver 实例
```python
for url in TARGET_URLS:
    driver = webdriver.Chrome()  # 启动 1-2s
    # ... 处理
    driver.quit()
```

**优化方案**：复用 driver 实例
```python
class DriverPool:
    def __init__(self, pool_size=3):
        self.drivers = [self._create_driver() for _ in range(pool_size)]
        self.available = set(self.drivers)
        self.lock = threading.Lock()
    
    def acquire(self):
        """获取可用 driver"""
        with self.lock:
            if self.available:
                driver = self.available.pop()
                self._clean_driver(driver)
                return driver
            raise Exception("No available drivers")
    
    def release(self, driver):
        """释放 driver"""
        with self.lock:
            self.available.add(driver)
    
    def _clean_driver(self, driver):
        """清理 driver 状态"""
        driver.delete_all_cookies()
        driver.execute_script("""
            localStorage.clear();
            sessionStorage.clear();
        """)

# 使用
pool = DriverPool(pool_size=5)
driver = pool.acquire()
try:
    # ... 处理逻辑
finally:
    pool.release(driver)
```

**效果**：
```
避免重复启动 Chrome，节省 1-2s/URL
```

---

#### 手段 4：并行化（Parallelization）

**当前问题**：串行处理 URL
```python
for url in TARGET_URLS:  # 串行
    process_url(url)
```

**优化方案**：并发处理多个 URL
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_parallel(urls, max_workers=3):
    """并行处理 URL 列表"""
    pool = DriverPool(pool_size=max_workers)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for url in urls:
            driver = pool.acquire()
            future = executor.submit(process_url, driver, url)
            futures[future] = driver
        
        for future in as_completed(futures):
            driver = futures[future]
            try:
                result = future.result()
                print(f"✅ 完成: {result}")
            except Exception as e:
                print(f"❌ 失败: {e}")
            finally:
                pool.release(driver)

# 使用
run_parallel(TARGET_URLS['fast'], max_workers=5)
```

**效果**：
```
串行：6 URL × 3 样本 × 0.8s = 14.4s
并行（3 workers）：14.4s / 3 = 4.8s
→ 提速 3 倍
```

---

### 2.3 综合提速效果

| 阶段 | 方法 | 单样本时间 | 10K 样本总时间 |
|------|------|-----------|---------------|
| **当前** | 串行 + 完整 reload | 3s | 8.3h |
| **+批量注入** | 5 samples/page | 1.2s | 3.3h |
| **+轻量重置** | 替代 reload | 0.8s | 2.2h |
| **+浏览器池** | 复用 driver | 0.6s | 1.7h |
| **+并行（5 workers）** | 并发处理 | 0.15s | 25min |

**最终目标**：10K 样本 < 30 分钟，100K 样本 < 5 小时

---

### 2.4 稳定性增强

#### 问题：Markdown 不一致

**现象**：
```
第 1 次访问 example.com：
  - 侧边栏有广告
  - 图片全部加载

第 2 次访问（不清 cache）：
  - 广告被拦截
  - 部分图片懒加载未触发

→ 注入到不同背景，配对不严格
```

**解决方案 1：清理浏览器状态**
```python
def _ensure_clean_state(self):
    """确保每次访问状态一致"""
    self.driver.delete_all_cookies()
    self.driver.execute_script("""
        localStorage.clear();
        sessionStorage.clear();
    """)
    
    # 可选：使用临时用户目录
    # chrome_options.add_argument(f"--user-data-dir=/tmp/chrome_{uuid.uuid4()}")
```

**解决方案 2：Markdown 一致性校验**
```python
def verify_page_consistency(self, url):
    """验证页面与历史版本一致"""
    current_html = self.driver.page_source
    current_hash = hashlib.md5(current_html.encode()).hexdigest()
    
    cached_hash = self.page_hashes.get(url)
    
    if cached_hash and cached_hash != current_hash:
        print(f"⚠️ {url} Markdown 已变更，跳过")
        return False
    
    self.page_hashes[url] = current_hash
    return True
```

**解决方案 3：增强弹窗清理**
```python
def remove_popups_aggressive(self):
    """激进清理干扰元素"""
    script = """
    (function() {
        // 1. 删除所有 fixed/sticky 元素
        document.querySelectorAll('[style*="position: fixed"], [style*="position: sticky"]')
            .forEach(el => el.remove());
        
        // 2. 删除已知干扰类名
        const keywords = ['cookie', 'popup', 'modal', 'banner', 'ads', 'overlay', 'consent'];
        document.querySelectorAll('*').forEach(el => {
            const cls = (el.className + ' ' + el.id).toLowerCase();
            if (keywords.some(kw => cls.includes(kw))) {
                el.remove();
            }
        });
        
        // 3. 删除所有 iframe（广告载体）
        document.querySelectorAll('iframe').forEach(el => {
            if (!el.src.includes('youtube') && !el.src.includes('vimeo')) {
                el.remove();
            }
        });
        
        // 4. 禁用弹窗函数
        window.alert = window.confirm = window.prompt = () => true;
        
        // 5. 修复 overflow
        document.body.style.overflow = 'auto';
        document.documentElement.style.overflow = 'auto';
    })();
    """
    self.driver.execute_script(script)
```

---

### 2.5 可行性总结

| 方面 | 行业方案 | 当前方案 | 改进后 | 评估 |
|------|---------|---------|--------|------|
| **速度** | 3s/样本 | 3s/样本 | 0.15s/样本（并发后） | ✅ 优秀 |
| **稳定性** | 低（商业站） | 中（文档站） | 高（一致性校验） | ✅ 可行 |
| **可重复性** | 差 | 中 | 高（Markdown hash） | ✅ 优秀 |
| **成本** | 高 | 中 | 低（并发优化） | ✅ 合理 |
| **样本质量** | 高（真实） | 高（真实） | 高（多维验证） | ✅ 优秀 |

**结论**：爬虫方案完全可行，优化后性能优于行业实践

---

## 🌐 多站点自适应加载
### 3.1 核心挑战

不同类型网站的加载特性差异巨大：

| 网站类别 | 典型加载时间 | DOM 复杂度 | 动态内容比例 | 推荐策略 |
|---------|-------------|-----------|-------------|---------|
| **文档类** | 1-2s | 低 | 0% | 激进优化 |
| **新闻/表单** | 2-5s | 中-高 | 20-40% | 平衡策略 |
| **电商/社交** | 4-10s | 极高 | 60-80% | 保守等待 |
| **工具/编辑器** | 5-15s | 极高 | 80-100% | 深度等待 |

**核心矛盾**：
- ❌ 固定等待 3s：快站点浪费时间，慢站点截图不完整
- ❌ 固定等待 10s：保险但低效（100K 样本需 28h）
- ✅ 自适应等待：根据站点类型动态调整

---

### 3.2 站点分档配置

```python
WEBSITE_PROFILES = {
    # ========== 快速档（文档类）==========
    "fast": {
        "urls": [
            "https://www.w3.org/",
            "https://docs.python.org/3/",
            "https://www.debian.org/",
            "https://www.ietf.org/",
            "https://en.wikipedia.org/wiki/Main_Page",
        ],
        "initial_wait": 1.5,              # 初始等待
        "max_wait": 4.0,                  # 最大等待
        "resource_timeout": 8.0,          # 资源加载超时
        "strategy": "document_ready",     # 等待策略
        "skip_resources": [               # 跳过的资源
            'image',      # 图片（用占位符）
            'media',      # 视频/音频
            'font',       # 字体（用系统字体）
        ],
        "concurrency": 8,                 # 最大并发数
        "samples_per_page": 5,            # 每页样本数
        "viewports": ['desktop'],         # 仅桌面
    },
    
    # ========== 中速档（新闻/表单）==========
    "medium": {
        "urls": [
            "https://www.bbc.com/",
            "https://www.reuters.com/",
            "https://developer.mozilla.org/",
            "https://stackoverflow.com/questions",
        ],
        "initial_wait": 3.0,
        "max_wait": 8.0,
        "resource_timeout": 15.0,
        "strategy": "custom_ready",       # 自定义条件
        "skip_resources": [
            'analytics',  # 追踪脚本
            'tracking',
            'ads',        # 广告
        ],
        "concurrency": 4,
        "samples_per_page": 3,
        "viewports": ['desktop', 'mobile'],
    },
    
    # ========== 慢速档（电商/社交）==========
    "slow": {
        "urls": [
            "https://www.amazon.com/",
            "https://www.ebay.com/",
            "https://github.com/trending",
        ],
        "initial_wait": 5.0,
        "max_wait": 15.0,
        "resource_timeout": 30.0,
        "strategy": "custom_ready_deep",  # 深度自定义
        "skip_resources": [
            'video',
            'cdn',
            'analytics',
            'ads',
            'tracking',
        ],
        "concurrency": 2,                 # 低并发避免限流
        "samples_per_page": 2,
        "viewports": ['desktop'],
    },
}

# 分辨率配置
VIEWPORT_CONFIGS = {
    "desktop": (1920, 1080),
    "tablet": (768, 1024),
    "mobile": (375, 667),
}
```

---

### 3.3 资源拦截（关键优化）

**核心思想**：不是所有资源都对 bug 检测有用，跳过无关资源可减少 30-50% 加载时间。

```python
class SmartResourceInterceptor:
    """智能资源拦截器"""
    
    def __init__(self, driver, skip_patterns=None):
        self.driver = driver
        self.skip_patterns = skip_patterns or []
        self.intercepted_count = 0
    
    def enable(self):
        """启用资源拦截"""
        blocklist = self._build_blocklist()
        
        script = f"""
        window.__interceptedRequests = [];
        window.__interceptedCount = 0;
        
        // 拦截 fetch
        const originalFetch = window.fetch;
        window.fetch = function(...args) {{
            const url = args[0];
            if (shouldSkip(url)) {{
                window.__interceptedRequests.push({{url, blocked: true}});
                window.__interceptedCount++;
                return Promise.resolve(new Response('', {{status: 304}}));
            }}
            return originalFetch.apply(this, args);
        }};
        
        // 拦截 XMLHttpRequest
        const originalXHR = window.XMLHttpRequest;
        window.XMLHttpRequest = function() {{
            const xhr = new originalXHR();
            const originalOpen = xhr.open;
            xhr.open = function(method, url, ...args) {{
                if (shouldSkip(url)) {{
                    window.__interceptedRequests.push({{url, blocked: true}});
                    window.__interceptedCount++;
                    xhr.readyState = 4;
                    xhr.status = 304;
                    return;
                }}
                return originalOpen.apply(this, [method, url, ...args]);
            }};
            return xhr;
        }};
        
        function shouldSkip(url) {{
            const blocklist = {blocklist};
            return blocklist.some(keyword => 
                url.toLowerCase().includes(keyword)
            );
        }}
        """
        
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': script
        })
    
    def _build_blocklist(self):
        """构建拦截列表"""
        base_patterns = {
            'image': ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico'],
            'font': ['.woff', '.woff2', '.ttf', '.otf', '.eot'],
            'video': ['.mp4', '.webm', '.ogg', '.mov'],
            'analytics': ['google-analytics', 'analytics.js', 'gtag', 'segment.com'],
            'tracking': ['mixpanel', 'amplitude', 'hotjar', 'fullstory'],
            'ads': ['doubleclick', 'pagead', 'adsystem', 'advertising'],
        }
        
        blocklist = []
        for pattern_type in self.skip_patterns:
            blocklist.extend(base_patterns.get(pattern_type, []))
        
        return blocklist
    
    def get_stats(self):
        """获取拦截统计"""
        count = self.driver.execute_script(
            "return window.__interceptedCount || 0;"
        )
        return {'intercepted_count': count}

# 使用
interceptor = SmartResourceInterceptor(
    driver,
    skip_patterns=['image', 'font', 'tracking', 'ads']
)
interceptor.enable()
driver.get(url)
stats = interceptor.get_stats()
print(f"拦截了 {stats['intercepted_count']} 个请求")
```

**效果示例**：
```
未拦截：加载 3.8s（112 个请求）
拦截后：加载 1.9s（34 个请求）
→ 减少 50% 时间
```

---

### 3.4 自适应等待策略

```python
class AdaptiveWaitManager:
    """自适应等待管理器"""
    
    def __init__(self, driver, profile='medium'):
        self.driver = driver
        self.profile = WEBSITE_PROFILES[profile]
        self.max_wait = self.profile['max_wait']
        self.wait = WebDriverWait(driver, self.max_wait)
    
    def wait_for_page_ready(self):
        """根据档位选择等待策略"""
        strategy = self.profile['strategy']
        
        if strategy == 'document_ready':
            return self._wait_fast()
        elif strategy == 'custom_ready':
            return self._wait_medium()
        elif strategy == 'custom_ready_deep':
            return self._wait_slow()
    
    def _wait_fast(self):
        """快速档：仅等待 DOM ready"""
        start = time.time()
        
        # 1. 等待 document.readyState === 'complete'
        self.wait.until(
            lambda d: d.execute_script(
                "return document.readyState === 'complete'"
            )
        )
        
        # 2. 等待主要内容容器出现
        try:
            self.wait.until(
                lambda d: d.execute_script("""
                    return document.querySelectorAll(
                        'main, article, .content, #content'
                    ).length > 0;
                """),
                timeout=2
            )
        except TimeoutException:
            pass  # 没有标准容器也可以
        
        elapsed = time.time() - start
        print(f"[fast] 等待 {elapsed:.2f}s")
        return elapsed
    
    def _wait_medium(self):
        """中速档：等待首屏内容可见"""
        start = time.time()
        
        # 1. DOM ready
        self.wait.until(
            lambda d: d.execute_script(
                "return document.readyState === 'complete'"
            )
        )
        
        # 2. 等待首屏元素达到阈值
        try:
            self.wait.until(
                lambda d: d.execute_script("""
                    const viewport = {
                        width: window.innerWidth,
                        height: window.innerHeight
                    };
                    const elements = document.querySelectorAll('*');
                    let visibleCount = 0;
                    
                    for (let el of elements) {
                        const rect = el.getBoundingClientRect();
                        if (rect.top < viewport.height && 
                            rect.bottom > 0 &&
                            rect.left < viewport.width && 
                            rect.right > 0) {
                            visibleCount++;
                        }
                    }
                    
                    return visibleCount > 50;  // 首屏至少 50 个可见元素
                """),
                timeout=5
            )
        except TimeoutException:
            print("[medium] 首屏元素超时，继续")
        
        # 3. 给 JS 初始化留点时间
        time.sleep(1)
        
        elapsed = time.time() - start
        print(f"[medium] 等待 {elapsed:.2f}s")
        return elapsed
    
    def _wait_slow(self):
        """慢速档：深度等待策略"""
        start = time.time()
        
        # 1. 基础 DOM ready
        self.wait.until(
            lambda d: d.execute_script(
                "return document.readyState === 'complete'"
            )
        )
        
        # 2. 等待关键选择器
        critical_selectors = [
            '[class*="product"]',
            '[class*="card"]',
            '[class*="item"]',
            '[class*="post"]',
            'article',
            '.content',
        ]
        
        for selector in critical_selectors:
            try:
                self.wait.until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, selector)) > 0,
                    timeout=2
                )
                break
            except TimeoutException:
                continue
        
        # 3. 等待 React/Vue 初始化
        try:
            self.wait.until(
                lambda d: d.execute_script("""
                    const root = document.querySelector(
                        '[data-reactroot], [data-v-app], #root, #app'
                    );
                    if (!root) return false;
                    
                    // 检查 React
                    const reactKey = Object.keys(root).find(k => 
                        k.startsWith('__react')
                    );
                    if (reactKey && root[reactKey].memoizedState) return true;
                    
                    // 检查 Vue
                    if (root.__vue__ && root.__vue__._data !== undefined) return true;
                    
                    return false;
                """),
                timeout=3
            )
        except TimeoutException:
            pass
        
        # 4. DOM 稳定性检测（懒加载完成）
        prev_count = 0
        stable_rounds = 0
        
        for _ in range(6):  # 最多 6 轮，每轮 0.5s
            current_count = self.driver.execute_script(
                "return document.querySelectorAll('*').length"
            )
            
            if current_count == prev_count:
                stable_rounds += 1
                if stable_rounds >= 3:  # 连续 3 轮稳定
                    break
            else:
                stable_rounds = 0
            
            prev_count = current_count
            time.sleep(0.5)
        
        elapsed = time.time() - start
        print(f"[slow] 等待 {elapsed:.2f}s (稳定轮数: {stable_rounds})")
        
        # 5. 超时保护
        if elapsed > self.max_wait:
            print(f"[slow] 超过最大等待 {self.max_wait}s，强制继续")
        
        return elapsed

# 使用
waiter = AdaptiveWaitManager(driver, profile='medium')
wait_time = waiter.wait_for_page_ready()
```

**效果对比**：
```
固定等待 8s：
  - 快站点浪费 6s
  - 慢站点可能不够

自适应等待：
  - 快站点 1.5-2s ✅
  - 中速站点 3-5s ✅
  - 慢速站点 6-12s ✅（有超时保护）
```

---

### 3.5 并发控制与负载均衡

```python
class AdaptiveConcurrencyManager:
    """自适应并发管理器"""
    
    def __init__(self):
        self.driver_pools = {
            'fast': [],
            'medium': [],
            'slow': [],
        }
        self.active_tasks = {}
        self.lock = threading.Lock()
    
    def create_pools(self):
        """创建驱动池"""
        for profile_type, config in WEBSITE_PROFILES.items():
            pool_size = config['concurrency']
            
            for i in range(pool_size):
                driver = self._create_driver(profile_type)
                self.driver_pools[profile_type].append(driver)
            
            print(f"✅ 创建 {profile_type} 池：{pool_size} 个 driver")
    
    def _create_driver(self, profile_type):
        """创建配置好的 driver"""
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        
        if profile_type == 'slow':
            # 慢速站点使用 User-Agent 轮换
            ua_list = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            ]
            options.add_argument(f'--user-agent={random.choice(ua_list)}')
        
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(WEBSITE_PROFILES[profile_type]['resource_timeout'])
        
        return driver
    
    def acquire(self, profile_type):
        """获取可用 driver（阻塞直到有可用）"""
        while True:
            with self.lock:
                pool = self.driver_pools[profile_type]
                for driver in pool:
                    if driver not in self.active_tasks.values():
                        task_id = str(uuid.uuid4())
                        self.active_tasks[task_id] = driver
                        return driver, task_id
            time.sleep(0.1)  # 等待
    
    def release(self, task_id):
        """释放 driver"""
        with self.lock:
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
    
    def cleanup(self):
        """清理所有 driver"""
        for pool in self.driver_pools.values():
            for driver in pool:
                try:
                    driver.quit()
                except:
                    pass

# 使用
mgr = AdaptiveConcurrencyManager()
mgr.create_pools()

driver, task_id = mgr.acquire('fast')
try:
    # ... 处理逻辑
finally:
    mgr.release(task_id)
```

---

### 3.6 异常处理与降级

```python
class RobustPageLoader:
    """鲁棒页面加载器：三级降级策略"""
    
    def __init__(self, driver, profile_type):
        self.driver = driver
        self.profile_type = profile_type
        self.max_retries = 3
    
    def load_with_fallback(self, url):
        """带降级的加载"""
        strategies = ['optimized', 'conservative', 'minimal']
        
        for retry in range(self.max_retries):
            strategy = strategies[retry]
            
            try:
                if strategy == 'optimized':
                    return self._load_optimized(url)
                elif strategy == 'conservative':
                    return self._load_conservative(url)
                elif strategy == 'minimal':
                    return self._load_minimal(url)
            
            except TimeoutException as e:
                print(f"[{strategy}] Timeout on {url}, 重试...")
                time.sleep(1 + retry)
            
            except Exception as e:
                print(f"[{strategy}] Error on {url}: {e}")
                self.driver.delete_all_cookies()
                time.sleep(2)
        
        print(f"❌ {url} 所有策略均失败，跳过")
        return False
    
    def _load_optimized(self, url):
        """策略1：优化加载"""
        # 启用资源拦截
        interceptor = SmartResourceInterceptor(
            self.driver,
            skip_patterns=WEBSITE_PROFILES[self.profile_type]['skip_resources']
        )
        interceptor.enable()
        
        # 加载页面
        self.driver.get(url)
        
        # 自适应等待
        waiter = AdaptiveWaitManager(self.driver, profile=self.profile_type)
        waiter.wait_for_page_ready()
        
        return True
    
    def _load_conservative(self, url):
        """策略2：保守加载"""
        # 只拦截追踪脚本
        interceptor = SmartResourceInterceptor(
            self.driver,
            skip_patterns=['tracking', 'analytics']
        )
        interceptor.enable()
        
        self.driver.get(url)
        time.sleep(3)  # 固定等待
        
        return True
    
    def _load_minimal(self, url):
        """策略3：极简加载"""
        self.driver.get(url)
        time.sleep(2)
        
        # 验证至少有 body
        body = self.driver.find_elements(By.TAG_NAME, 'body')
        if not body:
            raise Exception("No body element")
        
        return True

# 使用
loader = RobustPageLoader(driver, profile_type='medium')
success = loader.load_with_fallback(url)
```

---

### 3.7 性能对标

#### 场景：生成 100K 样本，覆盖 15 个站点，3 种分辨率

| 方案 | 单样本时间 | 并发数 | 总时间 | 说明 |
|------|-----------|-------|--------|------|
| **无优化** | 12s | 1 | 333h (14天) | 固定等待 8s + 无拦截 |
| **+资源拦截** | 7s | 1 | 194h | 减少 40% 加载时间 |
| **+自适应等待** | 4.5s | 1 | 125h | 避免无用等待 |
| **+批量注入** | 1.2s | 1 | 33h | 分摊加载成本 |
| **+并发(15)** | 1.2s | 15 | **2.2h** ✅ | 最终方案 |

**结论**：从 14 天 → 2.2 小时，加速 **150 倍**

---

## ✅ 质量验证体系
- 自动多维度校验：RMS 差异、直方图差异、SSIM 差异、边缘差异；按 bug 类型设置阈值（示例：Layout_Overlap 注重 RMS/SSIM，Color_Contrast 注重 SSIM/直方图，Text_Overflow 注重边缘差异）。
- 失败则丢弃样本并记录原因。
- 可选可视化：生成 HTML 报告，抽样 100 组展示 normal/buggy + 指标。

## 5) 成本与数据策略
- 路径对比：
  - 纯爬虫：质量高，速度中，需稳定性优化。
  - 纯合成（Canvas）：速度极快，质量低，泛化差。
  - 混合：质量最高，成本中高，推荐 60% 爬虫 + 40% 合成作为生产比例。
- 预期效果（参考文献与经验）：
  - 纯合成 F1 ≈ 55-67%；纯爬虫 73-81%；混合 79-84%。

## 6) 实施路线
- Week 1：
  - 增加 3 个高优先级 bug 类型。
  - 快站点小批量（1-2K）生成 → 人眼抽检 → 调阈值。
- Week 2：
  - 上线多维验证与轻量 reset；实现批量注入与浏览器池。
  - 跑 5K 样本；清洗低质样本。
- Week 3-4：
  - 按站点分档 + 自适应等待 + 资源拦截 + 并发池；覆盖多分辨率。
  - 生成 10K-20K 生产集；训练 baseline 模型，回测指标。
- 超大规模（>50K）：分布式/多机并发，定期 checkpoint，每 1K 持久化进度。

## 7) 关键检查清单
- [ ] fast/medium/slow 档位和并发配置已设定。
- [ ] 资源拦截生效（记录拦截数）。
- [ ] 自适应等待日志化（实际等待时长、触发策略、是否降级）。
- [ ] 每对样本记录：url、viewport、bug_type、验证指标、是否通过。
- [ ] 失败原因统计（候选为空、验证失败、超时、反爬）。
- [ ] 抽检报告生成并审核（至少 100 组）。

## 8) 关键代码片段（可直接嵌入）
- 轻量 reset：
  ```javascript
  // 清理注入样式并恢复 inline 样式
  document.querySelectorAll('[data-injected="true"]').forEach(el => el.remove());
  document.querySelectorAll('*').forEach(el => { el.style.cssText = ''; });
  ```
- Letter Spacing 注入示例：
  ```javascript
  const el = document.querySelector('p, h1, span');
  const spacings = ['-5px', '-2px', '0px', '12px', '24px'];
  if (el) el.style.letterSpacing = spacings[Math.floor(Math.random() * spacings.length)];
  ```
- Unnecessary Scroll 注入示例：
  ```javascript
  const body = document.body;
  body.style.width = `${window.innerWidth + 200}px`; // 强制水平滚动
  body.style.overflowX = 'visible';
  ```

## 9) 推荐优先级
1) 先补齐 3 个高优先级 bug 类型 + 自动验证。
2) 同步接入轻量 reset + 批量注入，立刻提升吞吐。
3) 再做站点分档、自适应等待、资源拦截、并发池。
4) 最后补充可选 bug 类型与可视化报告。

--
该一体化方案将“缺陷类型扩展”与“多站点高效爬取”合并，确保数据质量、效率、可重复性三者平衡。