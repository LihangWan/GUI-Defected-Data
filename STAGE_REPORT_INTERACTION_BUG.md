# 交互型 Bug 数据生成 - 阶段性报告

> 报告日期：2026年1月10日  
> 项目目标：为 LLM 微调生成高质量的 UI 交互 Bug 数据

---

## 一、项目背景

### 1.1 目标
构建一个自动化系统，在真实 Web 应用（OWASP Juice Shop）上模拟各类交互 Bug，生成包含：
- 操作前后截图（start/action/end）
- 元素语义信息（tag、id、class、aria-label、bbox）
- Bug 类型标签与描述
- 网络拦截日志、控制台错误日志

### 1.2 Bug 类型覆盖
| Bug 类型 | 描述 | 注入方式 |
|----------|------|----------|
| Navigation_Error | 点击后导航到错误页面 | 劫持 history.pushState |
| Timeout_Hang | 请求超时/页面卡住 | 网络延迟注入 |
| Operation_No_Response | 点击无响应 | 拦截网络请求 |
| Unexpected_Task_Result | 意外错误反馈（500错误） | 模拟服务端错误 |
| Silent_Failure | 静默失败（看似成功但无效果） | 返回空响应 |
| Validation_Error | 表单验证错误 | 注入非法数据 |

---

## 二、遇到的困难与挑战

### 2.1 元素选择问题

#### 问题描述
初期测试验证率仅 **11.5%**，分析发现大量样本的目标元素是 "OWASP Juice Shop" Logo 按钮，而非真正的交互元素。

#### 根本原因
1. **选择器过于宽泛**：`button, [role="button"], a[href]` 选中了导航栏和 Logo
2. **缺少有效性过滤**：未排除 OAuth 按钮、菜单按钮等非核心元素
3. **Angular Material 组件识别不足**：`mat-raised-button` 等组件未被正确选中

#### 解决方案
```python
# 增加 Angular Material 选择器
INTERACTIVE_SELECTORS = [
    "button[type='submit']",
    "[mat-raised-button]", "[mat-flat-button]",  # Angular Material
    "button:not([disabled])",
    # ...
]

# 过滤无效元素
def _is_valid_candidate(driver, el, allow_disabled_submit=False):
    # 排除 OAuth 按钮
    if any(kw in text for kw in ["google", "github", "twitter"]):
        return False
    # 排除网站 Logo
    if any(kw in text for kw in ["owasp", "juice shop"]):
        return False
    # 排除 menu 和 toolbar 按钮
    if "menu" in aria_label or in_toolbar:
        return False
```

### 2.2 Disabled 按钮问题

#### 问题描述
Juice Shop 的表单按钮（Login、Register、Submit）默认为 `disabled` 状态，CSS 设置 `pointer-events: none`，导致：
1. 元素被选择器过滤掉
2. 即使选中也无法点击

#### 解决方案
**思路转变**：不是绕过 disabled，而是让按钮变为 enabled。

```python
# 1. 允许选择 disabled 的提交按钮
def _is_valid_candidate(driver, el, allow_disabled_submit=False):
    if is_disabled:
        if allow_disabled_submit and is_submit_button:
            pass  # 允许
        else:
            return False

# 2. 自动填充表单使按钮 enabled
def _prefill_form_fields(self):
    """智能填充表单字段"""
    field_hints = {
        "email": "test@example.com",
        "password": "TestPass123!",
        "name": "Test User",
        # ...
    }
    # 填充 input/textarea
    # 处理 checkbox（如"同意条款"）
    # 处理 mat-select 下拉框
    # 触发 Angular 事件 (input/change/blur)
```

### 2.3 验证率低问题

#### 问题描述
即使注入成功，验证率仍然很低（约 17%），因为视觉验证条件过于严格。

#### 原始验证逻辑
```python
# Timeout_Hang 只看 spinner
visual_ok = has_spinner or ("loading" in text_after)
# 问题：登录失败后显示错误提示而非 spinner
```

#### 解决方案：审慎放宽 + console_logs 差异分析

```python
def _detect_visual_evidence(self, ..., console_logs_before, console_logs_after):
    # 1. 只统计点击后新增的 console 错误
    new_error_messages = []
    for log in console_logs_after:
        if log["timestamp"] not in before_timestamps:
            if log["level"] in ["SEVERE", "ERROR"]:
                new_error_messages.append(log["message"])
    
    # 2. 检测注入相关的 JS 错误
    injection_keywords = ["cannot read", "status", "timeout", "failed"]
    has_injection_related_error = any(
        kw in msg for kw in injection_keywords for msg in new_error_messages
    )
    
    # 3. 审慎放宽验证条件
    if bug_type == "Unexpected_Task_Result":
        visual_ok = (
            has_error_ele or 
            ("error" in text_after) or
            has_injection_related_error  # 新增：console错误也算
        )
```

### 2.4 网络拦截日志为空

#### 问题描述
所有样本的 `interceptor_logs` 都为空，无法作为注入成功的证据。

#### 根本原因
1. **XHR 请求未记录日志**：原实现只拦截 `fetch`，Juice Shop 大量使用 XHR
2. **延迟模式未记录日志**：`set_global_delay` 不记录拦截信息
3. **silent_failure 实现错误**：错误地设置 `error_urls['.*'] = 200`

#### 解决方案：增强 JS 拦截器 v2

```javascript
// XHR 也记录日志
XMLHttpRequest.prototype.send = function(...args) {
    const url = this._ice_url;
    if (config.timeout_urls.some(p => new RegExp(p).test(url))) {
        config.logs.push({type: 'timeout', url, method: 'xhr-' + method, timestamp: Date.now()});
        // ...
    }
    // 错误码拦截、延迟模式、静默模式都记录日志
};

// 新增 silent_mode
if (config.silent_mode) {
    config.logs.push({type: 'silent', url, method: 'fetch', timestamp: Date.now()});
    return new Response('', {status: 200});
}
```

---

## 三、思路演进

### 3.1 第一阶段：基础框架
- 实现 Selenium + JS 注入的基本流程
- 覆盖 6 种 Bug 类型
- **问题**：验证率极低，元素选择不准

### 3.2 第二阶段：元素选择优化
- 扩展测试路由（25+ 页面）
- 增加 Angular Material 选择器
- 实现元素有效性过滤
- **效果**：能选到正确的按钮，但仍有 disabled 问题

### 3.3 第三阶段：表单自动填充
- 实现 `_prefill_form_fields()` 智能表单填充
- 支持 checkbox、mat-select、radio 等组件
- 允许选择 disabled 提交按钮
- **效果**：按钮可点击，验证率提升至 17.6%

### 3.4 第四阶段：验证逻辑增强
- 收集点击前 console_logs 作为基线
- 分析新增的 JS 错误作为验证依据
- 修复网络拦截日志捕获
- **效果**：验证率提升至 **50%**

---

## 四、当前效果

### 4.1 数据统计
| 指标 | 初始值 | 当前值 | 提升 |
|------|--------|--------|------|
| 验证率 | 11.5% | **50.0%** | +38.5pp |
| 有网络日志的样本 | 0 | ~60% | - |
| Bug 类型覆盖 | 6 | 6 | - |
| 有效元素选择 | 差 | 良好 | - |

### 4.2 样本质量
```json
{
  "id": "int_41205855",
  "bug_type": "Unexpected_Task_Result",
  "element_semantic": {
    "tag": "button",
    "text": "exit_to_app\nLog in",
    "id": "loginButton",
    "aria_label": "Login"
  },
  "interceptor_logs": [
    {"type": "error", "url": "./rest/user/login", "code": 500, "method": "xhr-POST"}
  ],
  "visual_signals": {
    "has_network_logs": true,
    "has_injection_related_error": false
  },
  "injection_verified": true
}
```

### 4.3 Bug 类型分布
- Navigation_Error: 3
- Operation_No_Response: 1  
- Silent_Failure: 4
- Timeout_Hang: 3
- Unexpected_Task_Result: 4
- Validation_Error: 3

---

## 五、下一阶段规划

### 5.1 短期优化（1-2天）

#### 5.1.1 提升 Timeout_Hang 验证率
当前 Timeout_Hang 验证率仍较低，因为：
- 延迟模式不触发网络日志（请求最终会完成）
- 需要更长的等待时间来捕获 spinner

**计划**：
- 增加延迟后的等待时间
- 在延迟期间多次检测 spinner
- 考虑使用 timeout 拦截而非 delay

#### 5.1.2 增加页面覆盖
当前部分页面（search、track-result、chatbot）找不到有效元素。

**计划**：
- 分析这些页面的元素结构
- 针对性调整选择器
- 考虑登录后访问更多页面（如用户中心、订单历史）

#### 5.1.3 验证逻辑精细化
针对不同 Bug 类型定制更精准的验证条件。

### 5.2 中期目标（1周）

#### 5.2.1 多站点支持
当前仅支持 Juice Shop，计划支持：
- TodoMVC（Vue/React/Angular 版本）
- RealWorld App
- 其他开源 Web 应用

#### 5.2.2 数据增强
- 截图增强（随机裁剪、色彩抖动）
- 元素描述多样化
- Bug 描述模板扩展

#### 5.2.3 SFT 数据格式优化
当前 `train_sft.jsonl` 格式：
```json
{"instruction": "...", "input": "<image>", "output": "Bug Type: ..."}
```

计划增加：
- 多轮对话格式
- 思维链（CoT）格式
- 元素定位任务格式

### 5.3 长期目标（1月）

#### 5.3.1 自动质量评估
- 训练一个小模型评估样本质量
- 自动过滤低质量样本
- 反馈循环优化生成策略

#### 5.3.2 主动学习
- 识别模型预测不确定的样本
- 针对性生成补充数据
- 持续迭代提升

#### 5.3.3 真实 Bug 数据收集
- 从 Bug 追踪系统收集真实案例
- 与合成数据混合训练
- 评估真实 vs 合成数据的效果差异

---

## 六、关键经验总结

### 6.1 技术层面
1. **JS 注入比 CDP 更可靠**：Chrome DevTools Protocol 在 SPA 中行为不稳定
2. **Angular Material 需要特殊处理**：事件派发、mat-select 选择等
3. **验证需要多信号融合**：视觉变化 + 网络日志 + console 错误

### 6.2 方法论
1. **迭代式改进**：每次只解决一个问题，逐步提升
2. **审慎放宽**：放宽验证条件要有明确依据，避免引入噪声
3. **充分调试**：添加日志输出，理解系统行为

### 6.3 待解决的难点
1. **Navigation_Error 验证困难**：pushState 劫持后页面可能不显示 404
2. **Silent_Failure 本质难验证**：视觉上无变化，需要业务逻辑验证
3. **跨站点泛化**：不同框架/UI库的适配工作量大

---

## 附录：核心代码结构

```
interaction_engine/
├── injectors.py          # 核心注入引擎
│   ├── JSNetworkInterceptor    # JS 网络拦截器
│   ├── InteractionInjector     # 主注入类
│   │   ├── inject_*()          # 6种Bug注入方法
│   │   ├── _prefill_form_fields()  # 表单自动填充
│   │   └── _detect_visual_evidence()  # 验证逻辑
├── selector.py           # 元素选择器
│   ├── get_candidates()        # 通用候选元素
│   ├── get_network_triggering_candidates()  # 网络触发元素
│   └── _is_valid_candidate()   # 元素有效性检查
├── config.py             # 配置（路由、选择器）
└── capture.py            # 截图工具
```

---

*报告完成 - 2026年1月10日*
