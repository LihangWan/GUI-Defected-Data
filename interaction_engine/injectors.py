import os
import time
import uuid
import random
import json
from typing import List, Dict, Any
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from .config import (
    OUTPUT_DIR,
    IMG_INTERACTION_DIR,
    META_DIR,
    VIEWPORT_SIZE,
    LINK_DISCOVERY_LIMIT,
    LINK_SAMPLES_PER_PAGE,
)
from .capture import (
    visualize_action,
    ensure_dirs,
    bug_class,
    expected_behavior,
    show_overlay,
    three_frame_paths,
)
from .selector import get_candidates, get_network_triggering_candidates, discover_internal_links


class PageFeatureDetector:
    def __init__(self, driver: webdriver.Chrome, viewport_size: tuple[int, int] = VIEWPORT_SIZE):
        self.driver = driver
        self.viewport_size = viewport_size
        self.features: Dict[str, Any] = {}

    def scan_page(self) -> Dict[str, Any]:
        features: Dict[str, Any] = {}
        try:
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            forms = self.driver.find_elements(By.TAG_NAME, "form")
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            links = self.driver.find_elements(By.TAG_NAME, "a")

            features["has_inputs"] = len(inputs) > 0
            features["has_forms"] = len(forms) > 0
            features["has_buttons"] = len(buttons) > 0
            features["has_links"] = len(links) > 0
            features["form_count"] = len(forms)
            features["input_count"] = len(inputs)
            features["button_count"] = len(buttons)
            features["link_count"] = len(links)

            input_types: Dict[str, int] = {}
            for inp in inputs:
                try:
                    inp_type = (inp.get_attribute("type") or "text").lower()
                    input_types[inp_type] = input_types.get(inp_type, 0) + 1
                except Exception:
                    continue
            features["input_types"] = input_types

            features["page_type"] = self._infer_page_type(features)
            self.features = features
            return features
        except Exception as e:
            print(f"[!] Error scanning page: {e}")
            return {"page_type": "unknown", "has_inputs": False}

    def _infer_page_type(self, features: Dict[str, Any]) -> str:
        form_count = features.get("form_count", 0)
        input_count = features.get("input_count", 0)
        has_price = self._has_selector(["[class*='price']", "[class*='cart']", "[class*='checkout']"])
        if has_price and form_count > 0:
            return "ecommerce"
        if form_count >= 3 or input_count >= 10:
            return "form_heavy"
        if form_count > 0 or input_count > 0:
            return "interactive"
        return "static"

    def _has_selector(self, selectors: List[str]) -> bool:
        try:
            for selector in selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if len(elements) > 0:
                    return True
        except Exception:
            pass
        return False

    def get_allowed_bugs(self) -> List[str]:
        allowed = ["Navigation_Error"]
        page_type = self.features.get("page_type", "static")
        has_inputs = self.features.get("has_inputs", False)
        has_forms = self.features.get("has_forms", False)
        if page_type != "static":
            allowed += ["Timeout_Hang", "Operation_No_Response"]
        if has_forms or has_inputs:
            allowed += ["Validation_Error", "Unexpected_Task_Result", "Silent_Failure"]
        return allowed

    def get_bug_priority(self) -> Dict[str, float]:
        page_type = self.features.get("page_type", "static")
        input_count = self.features.get("input_count", 0)
        weights = {
            "Navigation_Error": 1.0,
            "Timeout_Hang": 1.0,
            "Validation_Error": 1.0,
            "Unexpected_Task_Result": 1.0,
            "Operation_No_Response": 1.0,
            "Silent_Failure": 1.0,
        }
        if page_type == "form_heavy":
            weights["Validation_Error"] = 3.0
            weights["Unexpected_Task_Result"] = 2.0
            weights["Silent_Failure"] = 1.5
        elif page_type == "ecommerce":
            weights["Validation_Error"] = 2.5
            weights["Unexpected_Task_Result"] = 2.5
            weights["Operation_No_Response"] = 1.5
        elif page_type == "interactive":
            weights["Operation_No_Response"] = 1.5
            weights["Timeout_Hang"] = 1.5
        if input_count > 5:
            weights["Validation_Error"] *= 1.5
        return weights

    def print_summary(self) -> None:
        print(f"\n{'='*60}")
        print(f"[PAGE FEATURE SUMMARY]")
        print(f"{'='*60}")
        print(f"Page Type: {self.features.get('page_type', 'unknown').upper()}")
        print(f"Forms: {self.features.get('form_count', 0)} | ", end="")
        print(f"Inputs: {self.features.get('input_count', 0)} | ", end="")
        print(f"Buttons: {self.features.get('button_count', 0)}")
        print(f"[+] Allowed Bugs: {', '.join(self.get_allowed_bugs())}")
        print(f"[W] Bug Weights: {self.get_bug_priority()}")
        print(f"{'='*60}\n")


class JSNetworkInterceptor:
    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver
        self.injection_state = {}

    def inject_fetch_interceptor(self) -> bool:
        script = """
        (function() {
            // 避免重复注入
            if (window.__ICE_INTERCEPTOR__ && window.__ICE_INTERCEPTOR__.injected) {
                return;
            }
            
            window.__ICE_INTERCEPTOR__ = {
                enabled: true,
                injected: true,
                timeout_urls: [],
                error_urls: {},
                delay_ms: 0,
                block_urls: [],
                silent_mode: false,  // 静默失败模式
                logs: []
            };

            window.__ORIGINAL_FETCH__ = window.__ORIGINAL_FETCH__ || window.fetch;
            window.__ORIGINAL_XHR_OPEN__ = window.__ORIGINAL_XHR_OPEN__ || XMLHttpRequest.prototype.open;
            window.__ORIGINAL_XHR_SEND__ = window.__ORIGINAL_XHR_SEND__ || XMLHttpRequest.prototype.send;

            window.fetch = async function(...args) {
                const url = typeof args[0] === 'string' ? args[0] : (args[0].url || '');
                const config = window.__ICE_INTERCEPTOR__;
                if (!config.enabled) {
                    return window.__ORIGINAL_FETCH__.apply(this, args);
                }
                
                // 超时拦截
                const isTimeout = config.timeout_urls.some(pattern => {
                    try { return new RegExp(pattern).test(url); } catch(e) { return false; }
                });
                if (isTimeout) {
                    config.logs.push({'type': 'timeout', 'url': url, 'method': 'fetch', 'timestamp': Date.now()});
                    return new Promise((resolve, reject) => {
                        setTimeout(() => { reject(new TypeError('Failed to fetch (timeout)')); }, 15000);
                    });
                }
                
                // 错误码拦截
                for (const [pattern, errorCode] of Object.entries(config.error_urls)) {
                    try {
                        if (new RegExp(pattern).test(url)) {
                            config.logs.push({'type': 'error', 'url': url, 'code': errorCode, 'method': 'fetch', 'timestamp': Date.now()});
                            return new Response(
                                JSON.stringify({'error': 'Server Error', 'code': errorCode}),
                                { status: errorCode, statusText: 'Error ' + errorCode, headers: { 'Content-Type': 'application/json' } }
                            );
                        }
                    } catch(e) {}
                }
                
                // 延迟模式
                if (config.delay_ms > 0) {
                    config.logs.push({'type': 'delay', 'url': url, 'delay_ms': config.delay_ms, 'method': 'fetch', 'timestamp': Date.now()});
                    await new Promise(resolve => setTimeout(resolve, config.delay_ms));
                }
                
                // 静默失败模式：返回空响应
                if (config.silent_mode) {
                    config.logs.push({'type': 'silent', 'url': url, 'method': 'fetch', 'timestamp': Date.now()});
                    return new Response('', { status: 200, statusText: 'OK', headers: { 'Content-Type': 'application/json' } });
                }
                
                return window.__ORIGINAL_FETCH__.apply(this, args);
            };

            XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                this._ice_url = url;
                this._ice_method = method;
                return window.__ORIGINAL_XHR_OPEN__.apply(this, [method, url, ...rest]);
            };

            XMLHttpRequest.prototype.send = function(...args) {
                const url = this._ice_url || '';
                const method = this._ice_method || 'GET';
                const config = window.__ICE_INTERCEPTOR__;
                const xhr = this;
                
                if (!config.enabled) {
                    return window.__ORIGINAL_XHR_SEND__.apply(this, args);
                }
                
                // 超时拦截
                const isTimeout = config.timeout_urls.some(pattern => {
                    try { return new RegExp(pattern).test(url); } catch(e) { return false; }
                });
                if (isTimeout) {
                    config.logs.push({'type': 'timeout', 'url': url, 'method': 'xhr-' + method, 'timestamp': Date.now()});
                    this.addEventListener('loadstart', () => {
                        setTimeout(() => xhr.abort(), 15000);
                    });
                    return window.__ORIGINAL_XHR_SEND__.apply(this, args);
                }
                
                // 错误码拦截（通过修改 onreadystatechange）
                for (const [pattern, errorCode] of Object.entries(config.error_urls)) {
                    try {
                        if (new RegExp(pattern).test(url)) {
                            config.logs.push({'type': 'error', 'url': url, 'code': errorCode, 'method': 'xhr-' + method, 'timestamp': Date.now()});
                            // 模拟错误响应
                            setTimeout(() => {
                                Object.defineProperty(xhr, 'status', { value: errorCode, writable: false });
                                Object.defineProperty(xhr, 'responseText', { value: JSON.stringify({'error': 'Server Error'}), writable: false });
                                Object.defineProperty(xhr, 'readyState', { value: 4, writable: false });
                                if (xhr.onreadystatechange) xhr.onreadystatechange();
                                if (xhr.onerror) xhr.onerror();
                            }, 100);
                            return;
                        }
                    } catch(e) {}
                }
                
                // 延迟模式
                if (config.delay_ms > 0) {
                    config.logs.push({'type': 'delay', 'url': url, 'delay_ms': config.delay_ms, 'method': 'xhr-' + method, 'timestamp': Date.now()});
                }
                
                // 静默失败模式
                if (config.silent_mode) {
                    config.logs.push({'type': 'silent', 'url': url, 'method': 'xhr-' + method, 'timestamp': Date.now()});
                    setTimeout(() => {
                        Object.defineProperty(xhr, 'status', { value: 200, writable: false });
                        Object.defineProperty(xhr, 'responseText', { value: '', writable: false });
                        Object.defineProperty(xhr, 'readyState', { value: 4, writable: false });
                        if (xhr.onreadystatechange) xhr.onreadystatechange();
                        if (xhr.onload) xhr.onload();
                    }, 100);
                    return;
                }
                
                return window.__ORIGINAL_XHR_SEND__.apply(this, args);
            };
            console.log('[ICE] Network interceptor injected (v2)');
        })();
        """
        try:
            self.driver.execute_script(script)
            self.injection_state["fetch_interceptor"] = True
            return True
        except Exception as e:
            print(f"[!] Failed to inject fetch interceptor: {e}")
            return False

    def intercept_request_timeout(self, url_pattern: str) -> bool:
        script = f"""
        (function() {{
            if (!window.__ICE_INTERCEPTOR__) return false;
            window.__ICE_INTERCEPTOR__.timeout_urls.push('{url_pattern}');
            return true;
        }})();
        """
        try:
            return self.driver.execute_script(script)
        except Exception:
            return False

    def intercept_request_error(self, url_pattern: str, error_code: int = 500) -> bool:
        script = f"""
        (function() {{
            if (!window.__ICE_INTERCEPTOR__) return false;
            window.__ICE_INTERCEPTOR__.error_urls['{url_pattern}'] = {error_code};
            return true;
        }})();
        """
        try:
            return self.driver.execute_script(script)
        except Exception:
            return False

    def set_global_delay(self, delay_ms: int) -> bool:
        script = f"""
        (function() {{
            if (!window.__ICE_INTERCEPTOR__) return false;
            window.__ICE_INTERCEPTOR__.delay_ms = {delay_ms};
            return true;
        }})();
        """
        try:
            return self.driver.execute_script(script)
        except Exception:
            return False

    def get_logs(self) -> List[Dict]:
        script = "return (window.__ICE_INTERCEPTOR__ && window.__ICE_INTERCEPTOR__.logs) ? window.__ICE_INTERCEPTOR__.logs : [];"
        try:
            logs = self.driver.execute_script(script)
            return logs if isinstance(logs, list) else []
        except Exception:
            return []

    def clear_logs(self) -> bool:
        """清空拦截日志"""
        script = """
        if (window.__ICE_INTERCEPTOR__) {
            window.__ICE_INTERCEPTOR__.logs = [];
            return true;
        }
        return false;
        """
        try:
            return self.driver.execute_script(script)
        except Exception:
            return False

    def reset_interceptor(self) -> bool:
        """重置所有拦截配置（但保留日志）"""
        script = """
        if (window.__ICE_INTERCEPTOR__) {
            window.__ICE_INTERCEPTOR__.timeout_urls = [];
            window.__ICE_INTERCEPTOR__.error_urls = {};
            window.__ICE_INTERCEPTOR__.delay_ms = 0;
            window.__ICE_INTERCEPTOR__.silent_mode = false;
            return true;
        }
        return false;
        """
        try:
            return self.driver.execute_script(script)
        except Exception:
            return False
        except Exception:
            return []


class InteractionInjector:
    def __init__(self, headless: bool = True, max_wait: int = 15, use_js_interceptor: bool = True,
                 show_overlay_flag: bool = True, debug_mode: bool = False):
        self.headless = headless
        self.max_wait = max_wait if not debug_mode else min(max_wait, 8)
        self.use_js_interceptor = use_js_interceptor
        self.show_overlay_flag = show_overlay_flag
        self.debug_mode = debug_mode
        self.driver = self._setup_driver()
        ensure_dirs()
        self.feature_detector = PageFeatureDetector(self.driver)
        self.js_interceptor = JSNetworkInterceptor(self.driver)

    def _setup_driver(self):
        options = Options()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument(f"--window-size={VIEWPORT_SIZE[0]},{VIEWPORT_SIZE[1]}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--ignore-certificate-errors")
        options.page_load_strategy = "eager"
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(15 if self.debug_mode else 30)
        return driver

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass

    def _wait_page_ready(self):
        try:
            WebDriverWait(self.driver, self.max_wait).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            print("[!] 页面加载等待超时，继续执行")
        
        # 🔥 关键：页面加载完成后立即注入网络拦截器
        if self.use_js_interceptor:
            success = self.js_interceptor.inject_fetch_interceptor()
            if success:
                print("  [✓] 网络拦截器已注入")
            else:
                print("  [✗] 网络拦截器注入失败")
        
        time.sleep(1 if self.debug_mode else 5)
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.2 if self.debug_mode else 0.5)
            self.driver.execute_script("window.scrollTo(0, 0);")
        except Exception:
            pass

    def _prefill_form_fields(self) -> None:
        """
        智能填充表单字段，使 disabled 按钮变为可用状态。
        支持多种输入类型和 Angular Material 组件。
        """
        filled_count = 0
        # 基础样本数据
        samples = {
            "text": "testuser",
            "email": "test@example.com", 
            "password": "TestPass123!",
            "search": "test query",
            "tel": "1234567890",
            "url": "https://example.com",
            "number": "42",
            "date": "2024-01-15",
            "datetime-local": "2024-01-15T10:30",
        }
        
        # 根据字段名/placeholder猜测合适的值
        field_hints = {
            "email": "test@example.com",
            "mail": "test@example.com",
            "user": "testuser123",
            "name": "Test User",
            "first": "John",
            "last": "Doe",
            "password": "TestPass123!",
            "pass": "TestPass123!",
            "confirm": "TestPass123!",
            "repeat": "TestPass123!",
            "phone": "1234567890",
            "tel": "1234567890",
            "mobile": "1234567890",
            "address": "123 Test Street",
            "city": "Test City",
            "zip": "12345",
            "postal": "12345",
            "country": "United States",
            "comment": "This is a test comment for form submission.",
            "message": "Test message content.",
            "subject": "Test Subject",
            "question": "What is your favorite color?",
            "answer": "Blue",
            "quantity": "1",
            "amount": "100",
        }
        
        try:
            # 1. 填充标准 input 和 textarea 字段
            fields = self.driver.find_elements(By.CSS_SELECTOR,
                "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='checkbox']):not([type='radio']):not([type='file']), textarea")
            
            for f in fields:
                try:
                    if not f.is_displayed():
                        continue
                    # 跳过已有值的字段
                    val = (f.get_attribute("value") or "").strip()
                    if val:
                        continue
                    
                    # 获取字段类型和标识
                    ftype = (f.get_attribute("type") or "text").lower()
                    fname = (f.get_attribute("name") or "").lower()
                    fid = (f.get_attribute("id") or "").lower()
                    fplaceholder = (f.get_attribute("placeholder") or "").lower()
                    flabel = (f.get_attribute("aria-label") or "").lower()
                    
                    # 综合判断字段用途
                    field_context = f"{fname} {fid} {fplaceholder} {flabel}"
                    
                    # 优先根据上下文选择值
                    sample = None
                    for hint_key, hint_val in field_hints.items():
                        if hint_key in field_context:
                            sample = hint_val
                            break
                    
                    # 否则根据类型选择默认值
                    if not sample:
                        sample = samples.get(ftype, "test input")
                    
                    # 清空并填充
                    f.clear()
                    f.send_keys(sample)
                    filled_count += 1
                    
                    # 触发 input/change 事件（Angular/React 需要）
                    self.driver.execute_script("""
                        const el = arguments[0];
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        el.dispatchEvent(new Event('blur', {bubbles: true}));
                    """, f)
                    
                except Exception:
                    continue
            
            # 2. 处理复选框（勾选必要的复选框，如"同意条款"）
            checkboxes = self.driver.find_elements(By.CSS_SELECTOR, 
                "input[type='checkbox'], mat-checkbox")
            for cb in checkboxes:
                try:
                    if not cb.is_displayed():
                        continue
                    # 检查是否已勾选
                    is_checked = cb.get_attribute("checked") or cb.get_attribute("aria-checked") == "true"
                    if is_checked:
                        continue
                    # 勾选
                    cb.click()
                except Exception:
                    continue
            
            # 3. 处理 Angular Material 下拉框 (mat-select)
            mat_selects = self.driver.find_elements(By.CSS_SELECTOR, "mat-select")
            for ms in mat_selects:
                try:
                    if not ms.is_displayed():
                        continue
                    # 检查是否已选择
                    selected = ms.get_attribute("aria-expanded")
                    value_text = ms.text.strip()
                    if value_text and value_text != "":
                        continue  # 已有选择
                    
                    # 点击打开下拉框
                    ms.click()
                    time.sleep(0.3)
                    
                    # 选择第一个选项
                    options = self.driver.find_elements(By.CSS_SELECTOR, "mat-option")
                    if options:
                        for opt in options:
                            if opt.is_displayed():
                                opt.click()
                                break
                    time.sleep(0.2)
                except Exception:
                    continue
            
            # 4. 处理单选按钮（选择第一个）
            radio_groups = {}
            radios = self.driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            for r in radios:
                try:
                    name = r.get_attribute("name")
                    if name and name not in radio_groups:
                        if r.is_displayed() and not r.is_selected():
                            r.click()
                            radio_groups[name] = True
                except Exception:
                    continue
            
            # 5. 短暂等待 Angular 响应
            time.sleep(0.3)
            
            if filled_count > 0:
                print(f"  [Prefill] Filled {filled_count} form field(s)")
            
        except Exception as e:
            # 静默失败，不影响主流程
            pass

    def _get_element_info(self, element) -> Dict[str, Any]:
        info = {"tag": element.tag_name.lower(), "text": "", "id": "", "class": "", "aria_label": "", "bbox": element.rect}
        try:
            txt = element.text.strip()
            if not txt:
                txt = element.get_attribute("value") or ""
            if not txt:
                txt = element.get_attribute("aria-label") or ""
            info["text"] = txt[:100] if txt else "Unknown Element"
        except Exception:
            info["text"] = "Unknown Element"
        for attr in ["id", "class", "aria-label"]:
            try:
                val = element.get_attribute(attr)
                if val:
                    key = attr.replace("-", "_")
                    info[key] = val[:120]
            except Exception:
                pass
        info["readable_name"] = self._readable_name(info)
        return info

    def _readable_name(self, info: Dict[str, Any]) -> str:
        if info.get("text") and info["text"] != "Unknown Element" and len(info["text"]) < 40:
            return f'"{info["text"]}"'
        if info.get("aria_label"):
            return f'"{info["aria_label"]}"'
        if info.get("id"):
            return f"{info['tag']}#{info['id']}"
        if info.get("class"):
            return f"{info['tag']}.{info['class'].split()[0]}"
        return info.get("tag", "element")

    # --- injectors ---
    def inject_operation_no_response(self, element):
        injection_success = False
        if self.use_js_interceptor:
            self.js_interceptor.inject_fetch_interceptor()
            self.js_interceptor.reset_interceptor()  # 清除之前的配置
            self.js_interceptor.clear_logs()  # 清除之前的日志
            injection_success = self.js_interceptor.intercept_request_timeout(r'.*')
            try:
                self.driver.execute_script(
                    "arguments[0].style.outline='3px solid #ff6b6b'; arguments[0].style.opacity='0.6';",
                    element,
                )
            except Exception:
                pass
        status = "✓ Injected" if injection_success else "✗ Failed"
        print(f"  [Inject] Operation_No_Response: {status}")
        return "Operation_No_Response", "Click initiated request but network was intercepted; no response received."

    def inject_navigation_error(self, element):
        # 清除之前的拦截配置
        if self.use_js_interceptor:
            self.js_interceptor.reset_interceptor()
            self.js_interceptor.clear_logs()
        try:
            self.driver.execute_script("""
                const orig_pushState = window.history.pushState;
                window.history.pushState = function(...args) {
                    console.log('[ICE] Navigation hijacked to:', args[2]);
                    args[2] = '/nonexistent-page-' + Math.random().toString(36).substr(2, 9);
                    return orig_pushState.apply(this, args);
                };
            """)
            print("  [Inject] Navigation_Error: ✓ Injected")
        except Exception as e:
            print(f"  [Inject] Navigation_Error: ✗ Failed - {e}")
        try:
            element.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)
        return "Navigation_Error", "Navigation hijacked; application loaded 404 or error page."

    def inject_unexpected_feedback(self, element):
        injection_success = False
        if self.use_js_interceptor:
            self.js_interceptor.inject_fetch_interceptor()
            self.js_interceptor.reset_interceptor()  # 清除之前的配置
            self.js_interceptor.clear_logs()  # 清除之前的日志
            injection_success = self.js_interceptor.intercept_request_error(r'.*', error_code=500)
        status = "✓ Injected" if injection_success else "✗ Failed"
        print(f"  [Inject] Unexpected_Task_Result: {status}")
        return "Unexpected_Task_Result", "API call returned 500 Internal Server Error; application error handler triggered."

    def inject_timeout_hang(self, element):
        injection_success = False
        if self.use_js_interceptor:
            self.js_interceptor.inject_fetch_interceptor()
            self.js_interceptor.reset_interceptor()  # 清除之前的配置
            self.js_interceptor.clear_logs()  # 清除之前的日志
            injection_success = self.js_interceptor.set_global_delay(15000)
        status = "✓ Injected" if injection_success else "✗ Failed"
        print(f"  [Inject] Timeout_Hang: {status}")
        return "Timeout_Hang", "Network latency simulated (15s); application shows loading spinner."

    def inject_silent_failure(self, element):
        injection_success = False
        if self.use_js_interceptor:
            self.js_interceptor.inject_fetch_interceptor()
            self.js_interceptor.reset_interceptor()  # 清除之前的配置
            self.js_interceptor.clear_logs()  # 清除之前的日志
            try:
                self.driver.execute_script("""
                    if (window.__ICE_INTERCEPTOR__) {
                        window.__ICE_INTERCEPTOR__.silent_mode = true;
                    }
                """)
                injection_success = True
            except Exception:
                injection_success = False
        status = "✓ Injected" if injection_success else "✗ Failed"
        print(f"  [Inject] Silent_Failure: {status}")
        return "Silent_Failure", "Request succeeded (200 OK) but response body was empty; operation silently failed."

    def inject_validation_error(self, element):
        inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='email'], input[type='number']")
        if inputs:
            target_input = random.choice(inputs)
            dirty_data = "@@@###!!!"
            try:
                target_input.clear()
                target_input.send_keys(dirty_data)
                self.driver.execute_script(
                    """
                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
                    """,
                    target_input,
                )
                print("  [Inject] Validation_Error: ✓ Injected (invalid data into input)")
            except Exception as e:
                print(f"  [Inject] Validation_Error: ✗ Failed - {e}")
            return "Validation_Error", "Injected invalid data into input field; application validation triggered."
        print("  [Inject] Validation_Error: ✗ No input fields found")
        return "Validation_Error", "Validation error triggered but no input field found on page."

    # --- visual evidence helpers ---
    def _dom_snapshot(self) -> Dict[str, Any]:
        """Capture lightweight DOM signals helpful for visual verification."""
        try:
            return self.driver.execute_script(
                r"""
                const textLimit = 5000;
                const takeText = () => {
                    const t = (document.body && document.body.innerText) ? document.body.innerText : '';
                    return t.slice(0, textLimit);
                };
                const anySel = (sels) => sels.some(s => document.querySelector(s));

                const spinnerSelectors = [
                    '.spinner', '.loading', '.loader', '.lds-ring', '.lds-dual-ring',
                    '.mat-progress-spinner', '.mat-mdc-progress-spinner', '.mat-progress-bar',
                    '.mdc-linear-progress', '.ngx-spinner', '.v-progress-circular'];
                const errorSelectors = [
                    '.error', '.mat-error', '.alert-danger', '.alert.alert-danger',
                    '.toast-error', '.snack-bar-error', '[role="alert"]', '.mdc-snackbar',
                    '.mat-snack-bar-container'];
                const validationSelectors = [
                    'input[aria-invalid="true"]', '.mat-form-field-invalid', '.ng-invalid.ng-touched'];

                const inputsInvalid = Array.from(document.querySelectorAll('input')).filter(
                    el => el.getAttribute('aria-invalid') === 'true'
                ).length;
                const title = document.title || '';
                const url = location.href;
                const text = takeText();

                return {
                    url,
                    title,
                    text,
                    has_spinner: anySel(spinnerSelectors),
                    has_error_ele: anySel(errorSelectors),
                    has_validation_ele: anySel(validationSelectors),
                    invalid_input_count: inputsInvalid,
                };
                """
            ) or {}
        except Exception as e:
            print(f"[!] DOM snapshot failed: {e}")
            return {}

    def _detect_visual_evidence(
        self, 
        bug_type: str, 
        before: Dict[str, Any], 
        after: Dict[str, Any], 
        interceptor_logs: List[Dict],
        console_logs_before: List[Dict] = None,
        console_logs_after: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        审慎的视觉验证：结合 DOM 变化、console_logs 差异和网络日志。
        只有当有明确证据时才判定为验证通过。
        """
        from difflib import SequenceMatcher
        def sim(a: str, b: str) -> float:
            try:
                return SequenceMatcher(None, a or "", b or "").ratio()
            except Exception:
                return 0.0

        similarity = sim(before.get("text", ""), after.get("text", ""))
        url_after = (after.get("url") or "").lower()
        title_after = (after.get("title") or "").lower()
        text_after = (after.get("text") or "").lower()
        has_logs = bool(interceptor_logs)
        
        # 分析 console_logs 差异：只统计点击后新增的错误
        new_console_errors = 0
        new_error_messages = []
        if console_logs_after:
            before_timestamps = set()
            if console_logs_before:
                before_timestamps = {log.get("timestamp", 0) for log in console_logs_before}
            
            for log in console_logs_after:
                # 只看新增的日志（timestamp 不在 before 中）
                if log.get("timestamp", 0) not in before_timestamps:
                    level = (log.get("level") or "").upper()
                    msg = (log.get("message") or "").lower()
                    # 只统计 SEVERE/ERROR 级别
                    if level in ["SEVERE", "ERROR"]:
                        # 排除一些常见的无关错误（如 favicon 404）
                        if "favicon" not in msg and "analytics" not in msg:
                            new_console_errors += 1
                            new_error_messages.append(msg[:100])
        
        # 判断是否有注入相关的 JS 错误（更可靠的信号）
        has_injection_related_error = False
        injection_error_keywords = [
            "cannot read", "undefined", "null", "typeerror", 
            "networkerror", "timeout", "failed to fetch", "status",
            "500", "502", "503", "504", "abort"
        ]
        for msg in new_error_messages:
            if any(kw in msg for kw in injection_error_keywords):
                has_injection_related_error = True
                break
        
        signals = {
            "similarity": round(similarity, 4),
            "has_spinner": bool(after.get("has_spinner")),
            "has_error_ele": bool(after.get("has_error_ele")),
            "has_validation_ele": bool(after.get("has_validation_ele")),
            "invalid_input_count": int(after.get("invalid_input_count", 0)),
            "has_network_logs": has_logs,
            "new_console_errors": new_console_errors,
            "has_injection_related_error": has_injection_related_error,
        }

        visual_ok = False
        
        if bug_type == "Navigation_Error":
            # 严格：必须看到 404 或 not found
            visual_ok = (
                "nonexistent-page-" in url_after or
                "404" in title_after or "not found" in title_after or
                "404" in text_after or "not found" in text_after
            )
            
        elif bug_type == "Timeout_Hang":
            # 主要信号：spinner、loading 文本
            # 辅助信号：有注入相关的 JS 错误（网络中断导致的错误）
            visual_ok = (
                signals["has_spinner"] or 
                ("loading" in text_after or "please wait" in text_after) or
                # 审慎放宽：有明确的注入相关错误也算成功
                # 包括：timeout/abort/failed 关键词，或者 status 相关错误（拦截导致 response 无 status）
                (has_injection_related_error and (
                    any(kw in str(new_error_messages) for kw in ["timeout", "abort", "failed"]) or
                    ("status" in str(new_error_messages) and "cannot read" in str(new_error_messages))
                ))
            )
            
        elif bug_type == "Operation_No_Response":
            # 严格：页面几乎没变化，且无错误显示
            visual_ok = similarity > 0.985 and not signals["has_error_ele"] and not signals["has_spinner"]
            
        elif bug_type == "Unexpected_Task_Result":
            # 主要信号：页面显示错误元素或错误文本
            # 辅助信号：有新增的 console 错误（且是注入相关的）
            visual_ok = (
                signals["has_error_ele"] or 
                ("error" in title_after or "error" in text_after or "500" in text_after) or
                # 审慎放宽：有明确的注入相关 JS 错误
                has_injection_related_error
            )
            
        elif bug_type == "Silent_Failure":
            # 静默失败本身难以视觉验证，保持原有逻辑
            visual_ok = similarity > 0.985 and not signals["has_error_ele"] and not signals["has_spinner"]
            
        elif bug_type == "Validation_Error":
            # 验证错误：显示验证元素或 invalid 输入
            visual_ok = (
                signals["has_validation_ele"] or 
                signals["invalid_input_count"] > 0 or 
                ("invalid" in text_after) or
                ("required" in text_after and signals["has_error_ele"])
            )

        return {"visual_verified": bool(visual_ok), "signals": signals}
    def execute_injection(self, element, bug_choice: str | None = None):
        uid = f"int_{uuid.uuid4().hex[:8]}"
        bug_type = "Unknown"
        desc = "Injection failed"
        t0_action_path = None
        t1_path = None
        t0_clean_path = None
        before_dom: Dict[str, Any] = {}
        after_dom: Dict[str, Any] = {}
        elem_info = {"tag": "unknown", "text": "", "id": "", "class": "", "aria_label": "", "bbox": {}}
        center_x, center_y = 0, 0

        bug_name_mapping = {
            "Navigation_Error": "nav_error",
            "Timeout_Hang": "timeout",
            "Operation_No_Response": "no_response",
            "Validation_Error": "validation",
            "Unexpected_Task_Result": "fake_error",
            "Silent_Failure": "silent",
        }
        display_name_from_key = {
            "nav_error": "Navigation_Error",
            "timeout": "Timeout_Hang",
            "no_response": "Operation_No_Response",
            "validation": "Validation_Error",
            "fake_error": "Unexpected_Task_Result",
            "silent": "Silent_Failure",
        }
        if bug_choice and bug_choice in bug_name_mapping:
            bug_type_key = bug_name_mapping[bug_choice]
        else:
            bug_type_key = random.choice(list(bug_name_mapping.values()))

        try:
            t0_clean_path, t0_action_path, t1_path = three_frame_paths(uid)
            # T0 clean screenshot
            self.driver.save_screenshot(t0_clean_path)
            # DOM snapshot before click for visual verification
            before_dom = self._dom_snapshot()
            # Prefill to avoid empty submissions
            self._prefill_form_fields()

            # 收集点击前的 console_logs 作为基线
            console_logs_before = []
            try:
                console_logs_before = self.driver.get_log("browser")
            except Exception:
                pass

            elem_info = self._get_element_info(element)
            rect = self.driver.execute_script(
                """
                const el = arguments[0];
                el.scrollIntoView({behavior:'instant', block:'center', inline:'center'});
                const r = el.getBoundingClientRect();
                return {x: r.x, y: r.y, width: r.width, height: r.height, page_x: r.x + window.scrollX, page_y: r.y + window.scrollY};
            """,
                element,
            )
            elem_info["bbox"] = {
                "x": rect.get("page_x", 0),
                "y": rect.get("page_y", 0),
                "width": rect.get("width", 0),
                "height": rect.get("height", 0),
            }
            center_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
            center_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)

            # T0 action with pointer AND Label
            # Pass the intended bug type key as label (e.g. "Timeout_Hang" from key "timeout")
            visual_label = display_name_from_key.get(bug_type_key, "Interaction")
            visualize_action(t0_clean_path, center_x, center_y, output_path=t0_action_path, label=visual_label)
            print(f"  [Action] Overlay visualized: {visual_label}")

            print(f"  [Execute] Bug type: {bug_type_key} → {display_name_from_key.get(bug_type_key, bug_type_key)}")

            if bug_type_key == "no_response":
                bug_type, desc = self.inject_operation_no_response(element)
            elif bug_type_key == "nav_error":
                bug_type, desc = self.inject_navigation_error(element)
            elif bug_type_key == "fake_error":
                bug_type, desc = self.inject_unexpected_feedback(element)
            elif bug_type_key == "timeout":
                bug_type, desc = self.inject_timeout_hang(element)
            elif bug_type_key == "silent":
                bug_type, desc = self.inject_silent_failure(element)
            else:
                bug_type, desc = self.inject_validation_error(element)
            
            print(f"  [Injected] bug_type={bug_type}, desc={desc[:60]}...")

            # Ensure overlay shows a meaningful label even if later steps fail
            overlay_bug = bug_type if bug_type != "Unknown" else display_name_from_key.get(bug_type_key, bug_choice or "Unknown")
            print(f"  [Overlay] Setting overlay: {overlay_bug}")

            if self.show_overlay_flag:
                show_overlay(self.driver, overlay_bug, desc or "Injected interaction")

            try:
                element.click()
                print(f"  [Click] Successfully clicked element")
            except Exception:
                try:
                    self.driver.execute_script("arguments[0].click();", element)
                    print(f"  [Click] JS click fallback successful")
                except Exception:
                    print("[!] Click fallback failed, skip element")
                    return
            time.sleep(0.5 if self.debug_mode else 2)
            after_dom = self._dom_snapshot()

        except Exception as e:
            print(f"[!] Failed to inject on element: {e}")
        finally:
            # Remove JS overlay before taking end screenshot
            try:
                self.driver.execute_script("""
                    const overlay = document.getElementById('__ICE_BUG_OVERLAY__');
                    if (overlay) overlay.remove();
                """)
            except:
                pass
            
            # End screenshot (no longer need JS overlay, using static red tag instead)
            try:
                t1_temp_path = t1_path.replace("_end.png", "_end_temp.png")
                self.driver.save_screenshot(t1_temp_path)
                # Add red tag to end screenshot (same as action)
                safe_bug_label = bug_type if bug_type != "Unknown" else display_name_from_key.get(bug_type_key, bug_choice or "Unknown")
                visualize_action(t1_temp_path, 0, 0, output_path=t1_path, label=safe_bug_label)
                # Clean up temp file
                try:
                    os.remove(t1_temp_path)
                except:
                    pass
                print(f"  [Screenshot] End screenshot with red tag saved")
            except Exception as e:
                print(f"  [Screenshot] Failed to save end screenshot: {e}")
                t1_path = None

            if t0_action_path and t1_path and bug_type != "Unknown":
                # DOM snapshot after interaction (post overlay cleanup)
                if not after_dom:
                    after_dom = self._dom_snapshot()

                console_logs_after = []
                try:
                    console_logs_after = self.driver.get_log("browser")
                except Exception:
                    console_logs_after = []

                interceptor_logs = []
                if self.use_js_interceptor:
                    interceptor_logs = self.js_interceptor.get_logs()

                # Visual + network + console evidence
                visual_eval = {}
                visual_verified = False
                try:
                    before_safe = before_dom if isinstance(before_dom, dict) else {}
                    after_safe = after_dom if isinstance(after_dom, dict) else {}
                    visual_eval = self._detect_visual_evidence(
                        bug_type, 
                        before_safe, 
                        after_safe, 
                        interceptor_logs,
                        console_logs_before=console_logs_before,
                        console_logs_after=console_logs_after
                    )
                    visual_verified = bool(visual_eval.get("visual_verified", False))
                except Exception as e:
                    print(f"[!] Visual evaluation failed: {e}")
                    visual_eval = {}
                    visual_verified = False
                
                # 合并 console_logs 用于存储
                console_logs = console_logs_after

                has_network_logs = len(interceptor_logs) > 0
                injection_verified = False
                if bug_type in ["Navigation_Error", "Validation_Error"]:
                    injection_verified = visual_verified or has_network_logs
                elif has_network_logs:
                    injection_verified = True
                else:
                    injection_verified = visual_verified

                meta = {
                    "id": uid,
                    "bug_category": "interaction",
                    "bug_type": bug_type,
                    "bug_class": bug_class(bug_type),
                    "description": desc,
                    "expected_behavior": expected_behavior(bug_type),
                    "url": self.driver.current_url,
                    "element_semantic": elem_info,
                    "action_trace": {
                        "action": "click",
                        "coordinates": [center_x, center_y],
                        "target_readable": elem_info.get("readable_name"),
                    },
                    "images": {
                        "start": os.path.relpath(t0_clean_path, OUTPUT_DIR).replace("\\", "/"),
                        "action": os.path.relpath(t0_action_path, OUTPUT_DIR).replace("\\", "/"),
                        "end": os.path.relpath(t1_path, OUTPUT_DIR).replace("\\", "/"),
                    },
                    "console_logs": console_logs,
                    "interceptor_logs": interceptor_logs,
                    "timestamp": str(datetime.now()),
                    "injection_verified": injection_verified,
                    "visual_verified": visual_verified,
                    "visual_signals": visual_eval.get("signals", {}),
                    "has_network_logs": len(interceptor_logs) > 0,
                }
                try:
                    meta_path = os.path.join(META_DIR, f"{uid}.json")
                    with open(meta_path, "w", encoding="utf-8") as f:
                        json.dump(meta, f, ensure_ascii=False, indent=2)
                    status = "✓" if meta.get("injection_verified") else "?"
                    print(f"{status} [Stored] Interaction {uid} | Bug: {bug_type} | Logs: {len(interceptor_logs)}")
                except Exception as e:
                    print(f"[!] Failed to write metadata: {e}")

    def run_on_url(self, url: str, samples_per_site: int = 8):
        print(f"[*] Loading: {url}")
        self.driver.get(url)
        self._wait_page_ready()
        self.feature_detector.scan_page()
        self.feature_detector.print_summary()

        allowed_bugs = self.feature_detector.get_allowed_bugs()
        bug_weights = self.feature_detector.get_bug_priority()
        if not allowed_bugs:
            print("[-] No allowed bugs for this page type")
            return

        # 获取两种候选元素
        base_candidates = get_candidates(self.driver, prioritize_network=True)
        network_candidates = get_network_triggering_candidates(self.driver)
        
        print(f"[*] 找到 {len(base_candidates)} 个通用候选元素")
        print(f"[*] 找到 {len(network_candidates)} 个网络触发元素")
        
        if not base_candidates and not network_candidates:
            print("[-] No valid interactive elements, skip")
            return

        # 网络类Bug列表
        network_bugs = {"Timeout_Hang", "Operation_No_Response", "Unexpected_Task_Result", "Silent_Failure"}

        bug_choices = list(bug_weights.keys())
        raw_weights = list(bug_weights.values())
        if raw_weights:
            min_w = min(raw_weights)
            max_w = max(raw_weights)
            if max_w > 0 and min_w > 0 and max_w / min_w > 5:
                weights = [max(0.5, w * 0.5 + 1) for w in raw_weights]
            else:
                weights = raw_weights
        else:
            weights = [1.0] * len(bug_choices)

        bug_plan = list(bug_choices)
        while len(bug_plan) < samples_per_site:
            bug_plan.append(random.choices(bug_choices, weights=weights)[0])
        random.shuffle(bug_plan)

        for i in range(samples_per_site):
            try:
                chosen_bug = bug_plan[i % len(bug_plan)]
                
                # 🔥 每次迭代重新获取元素（避免stale element reference）
                current_base = get_candidates(self.driver, prioritize_network=True)
                current_network = get_network_triggering_candidates(self.driver)
                
                # 根据Bug类型选择合适的候选元素
                if chosen_bug in network_bugs and current_network:
                    # 网络类Bug用网络触发元素
                    candidates = current_network
                    print(f"  [选择] {chosen_bug} → 使用网络触发元素 ({len(candidates)}个)")
                else:
                    # 其他Bug用通用元素
                    candidates = current_base if current_base else current_network
                    print(f"  [选择] {chosen_bug} → 使用通用元素 ({len(candidates)}个)")
                
                if not candidates:
                    print(f"  [跳过] 无可用元素")
                    continue
                
                # 随机选择一个元素
                target = random.choice(candidates)
                
                self.execute_injection(target, bug_choice=chosen_bug)

                self.driver.get(url)
                self._wait_page_ready()
            except Exception as e:
                print(f"[!] Error in iteration {i}: {e}")
                self.driver.get(url)
                self._wait_page_ready()
                continue

    def run_batch(self, targets: Dict[str, Dict], samples_per_site: int = 6, enable_discovery: bool = True,
                  link_limit: int = LINK_DISCOVERY_LIMIT, link_samples: int = LINK_SAMPLES_PER_PAGE):
        for name, cfg in targets.items():
            base = cfg.get("base")
            routes = cfg.get("routes", [])
            if not base:
                continue
            try:
                self.run_on_url(base, samples_per_site)
                for r in routes:
                    full = r if r.startswith("http") else base.rstrip("/") + r
                    self.run_on_url(full, samples_per_site=max(2, link_samples))
                if enable_discovery:
                    try:
                        self.driver.get(base)
                        self._wait_page_ready()
                    except Exception:
                        pass
                    links = discover_internal_links(self.driver, base, limit=link_limit)
                    for link in links:
                        self.run_on_url(link, samples_per_site=max(2, link_samples))
            except Exception as e:
                print(f"[!] Failed on {name}: {e}")
