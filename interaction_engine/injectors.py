import os
import sys
import time
import uuid
import random
import json
import numpy as np
from typing import List, Dict, Any
from datetime import datetime

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass  # Python < 3.7

try:
    import cv2
    from skimage.metrics import structural_similarity as ssim
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
try:
    from PIL import Image, ImageChops
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

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
from .visual_styles import (
    generate_404_page_js,
    generate_loading_overlay_js,
    generate_error_toast_js,
    get_random_404_style,
    get_random_loading_style,
    get_random_error_toast_style,
)


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
        """Return allowed bug types based on Big Three taxonomy.
        
        Bug Types (ICE-Web Big Three):
        - Navigation_Error: User clicks but redirected to 404/wrong route
        - Operation_No_Response: Click fails to produce expected outcome (dead click/timeout)
        - Unexpected_Task_Result: System returns visible error (500 response)
        """
        allowed = ["Navigation_Error"]
        page_type = self.features.get("page_type", "static")
        has_inputs = self.features.get("has_inputs", False)
        has_forms = self.features.get("has_forms", False)
        if page_type != "static":
            allowed += ["Operation_No_Response"]
        if has_forms or has_inputs:
            allowed += ["Unexpected_Task_Result"]
        return allowed

    def get_bug_priority(self) -> Dict[str, float]:
        """Get bug type weights based on page characteristics.
        
        Big Three Bug Types only:
        - Navigation_Error: Always available
        - Operation_No_Response: For dynamic/interactive pages
        - Unexpected_Task_Result: For pages with forms/API interactions
        """
        page_type = self.features.get("page_type", "static")
        weights = {
            "Navigation_Error": 1.0,
            "Unexpected_Task_Result": 1.0,
            "Operation_No_Response": 1.2,
        }
        if page_type == "form_heavy":
            weights["Unexpected_Task_Result"] = 2.5
        elif page_type == "ecommerce":
            weights["Unexpected_Task_Result"] = 2.5
            weights["Operation_No_Response"] = 1.5
        elif page_type == "interactive":
            weights["Operation_No_Response"] = 1.5
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


class NativeErrorPageDetector:
    """检测网站是否有原生错误页面、加载动画和错误提示
    
    优先使用网站原生的错误页面，这样可以：
    1. 提高多样性，避免模型过拟合
    2. 更真实地模拟实际 bug 场景
    3. 每个网站的 404/500 页面都不同
    """
    
    # 常见的 404 路径模式
    COMMON_404_PATHS = [
        '/404',
        '/error/404', 
        '/not-found',
        '/page-not-found',
        '/nonexistent-test-page-xyz123',
    ]
    
    # 404 页面内容特征
    ERROR_404_KEYWORDS = [
        '404', 'not found', 'page not found', 'does not exist',
        'cannot be found', 'couldn\'t find', 'no longer exists',
        'removed', 'deleted', 'unavailable', 'missing page',
        '找不到', '页面不存在', '页面丢失',
    ]
    
    # 加载动画 CSS 选择器
    LOADING_SELECTORS = [
        '.spinner', '.loading', '.loader', '.progress',
        '.mat-progress-spinner', '.mat-mdc-progress-spinner',
        '.mat-progress-bar', '.mdc-linear-progress',
        '.ngx-spinner', '.v-progress-circular', '.el-loading',
        '[class*="spinner"]', '[class*="loading"]', '[class*="loader"]',
        '.sk-circle', '.lds-ring', '.lds-dual-ring',
    ]
    
    # 错误提示 CSS 选择器
    ERROR_TOAST_SELECTORS = [
        '.toast', '.notification', '.alert', '.snackbar',
        '.mat-snack-bar-container', '.mdc-snackbar',
        '.v-toast', '.el-message', '.ant-message',
        '[class*="toast"]', '[class*="notification"]',
        '[class*="error"]', '[class*="alert"]',
    ]
    
    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver
        self._cache: Dict[str, Dict[str, Any]] = {}  # 按域名缓存检测结果
    
    def _get_domain(self, url: str) -> str:
        """提取域名用于缓存"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
        except:
            return url.split('/')[0:3]
    
    def detect_native_404(self, base_url: str) -> Dict[str, Any]:
        """检测网站是否有原生 404 页面
        
        Returns:
            {
                'has_native_404': bool,
                'native_404_url': str or None,
                'detection_method': str,
                'visual_change_pct': float,
            }
        """
        domain = self._get_domain(base_url)
        cache_key = f"{domain}:404"
        
        # 检查缓存
        if cache_key in self._cache:
            print(f"  [Cache] 使用缓存的 404 检测结果: {self._cache[cache_key]['has_native_404']}")
            return self._cache[cache_key]
        
        result = {
            'has_native_404': False,
            'native_404_url': None,
            'detection_method': 'none',
            'visual_change_pct': 0.0,
        }
        
        try:
            # 保存当前 URL 和页面状态
            original_url = self.driver.current_url
            original_title = self.driver.title
            
            # 获取首页截图用于对比
            try:
                self.driver.get(base_url)
                time.sleep(1)
                home_screenshot = self.driver.get_screenshot_as_png()
            except:
                home_screenshot = None
            
            # 尝试访问不存在的页面
            for test_path in self.COMMON_404_PATHS:
                test_url = f"{domain}{test_path}"
                try:
                    self.driver.get(test_url)
                    time.sleep(1.5)
                    
                    # 检查页面内容
                    page_source = self.driver.page_source.lower()
                    body_text = ""
                    try:
                        body_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
                    except:
                        pass
                    
                    # 方法1: 检查 HTTP 状态码 (通过 JavaScript)
                    # 注意: SPA 通常不会返回真正的 404 状态码
                    
                    # 方法2: 检查页面内容是否包含 404 关键词
                    has_404_keyword = any(kw.lower() in body_text or kw.lower() in page_source 
                                          for kw in self.ERROR_404_KEYWORDS)
                    
                    # 方法3: 检查页面视觉是否与首页不同
                    visual_different = False
                    if home_screenshot and HAS_PIL:
                        try:
                            current_screenshot = self.driver.get_screenshot_as_png()
                            from io import BytesIO
                            img1 = Image.open(BytesIO(home_screenshot))
                            img2 = Image.open(BytesIO(current_screenshot))
                            diff = ImageChops.difference(img1, img2)
                            diff_pixels = sum(sum(p) > 0 for p in diff.getdata())
                            total_pixels = img1.width * img1.height
                            change_pct = (diff_pixels / total_pixels) * 100
                            result['visual_change_pct'] = change_pct
                            visual_different = change_pct > 30  # 超过30%变化
                        except:
                            pass
                    
                    # 判断是否是原生 404
                    if has_404_keyword and visual_different:
                        result['has_native_404'] = True
                        result['native_404_url'] = test_url
                        result['detection_method'] = 'keyword+visual'
                        print(f"  [Detect] 发现原生 404 页面: {test_url}")
                        break
                    elif has_404_keyword:
                        result['has_native_404'] = True
                        result['native_404_url'] = test_url
                        result['detection_method'] = 'keyword'
                        print(f"  [Detect] 发现原生 404 页面 (关键词匹配): {test_url}")
                        break
                    elif visual_different and result['visual_change_pct'] > 50:
                        # 视觉变化很大，可能是错误页面
                        result['has_native_404'] = True
                        result['native_404_url'] = test_url
                        result['detection_method'] = 'visual'
                        print(f"  [Detect] 发现可能的 404 页面 (视觉变化 {result['visual_change_pct']:.1f}%): {test_url}")
                        break
                        
                except Exception as e:
                    # 如果访问出错 (真正的 404 HTTP 错误)，这可能是原生 404
                    print(f"  [Detect] 访问 {test_url} 出错: {e}")
                    continue
            
            # 返回原页面
            try:
                self.driver.get(original_url)
                time.sleep(0.5)
            except:
                pass
                
        except Exception as e:
            print(f"  [Detect] 404 检测失败: {e}")
        
        # 缓存结果
        self._cache[cache_key] = result
        
        if not result['has_native_404']:
            print(f"  [Detect] 未发现原生 404 页面，将使用注入样式")
        
        return result
    
    def detect_native_loading(self) -> Dict[str, Any]:
        """检测页面是否有原生加载动画组件
        
        策略：
        1. 检测页面中是否存在 loading/spinner 相关的 CSS 类或元素
        2. 检测是否有隐藏的 loading overlay 可以被激活
        """
        result = {
            'has_native_loading': False,
            'loading_selectors': [],
            'can_trigger_native': False,
            'trigger_method': None,
        }
        
        try:
            # 方法1：检测现有的 loading 元素（可能是隐藏的）
            for selector in self.LOADING_SELECTORS:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        result['has_native_loading'] = True
                        result['loading_selectors'].append(selector)
                except:
                    continue
            
            # 方法2：检测是否有可以触发的 loading 机制
            # 检查是否有 Angular/React/Vue 的 loading 服务
            native_loading_check = self.driver.execute_script("""
                // Angular Material
                if (window.ng && document.querySelector('mat-progress-spinner, mat-progress-bar')) {
                    return { framework: 'angular-material', available: true };
                }
                // ngx-spinner
                if (window.NgxSpinnerService || document.querySelector('ngx-spinner')) {
                    return { framework: 'ngx-spinner', available: true };
                }
                // Vue loading
                if (window.Vue && document.querySelector('.v-progress-circular, .el-loading-mask')) {
                    return { framework: 'vue', available: true };
                }
                // 通用：检测隐藏的 loading overlay
                const hiddenLoaders = document.querySelectorAll(
                    '[class*="loading"][style*="display: none"], ' +
                    '[class*="spinner"][style*="display: none"], ' +
                    '[class*="overlay"][style*="visibility: hidden"]'
                );
                if (hiddenLoaders.length > 0) {
                    return { framework: 'hidden-overlay', available: true, selector: hiddenLoaders[0].className };
                }
                return { available: false };
            """)
            
            if native_loading_check and native_loading_check.get('available'):
                result['can_trigger_native'] = True
                result['trigger_method'] = native_loading_check.get('framework')
                print(f"  [Detect] 发现原生 Loading 机制: {native_loading_check.get('framework')}")
                
        except Exception as e:
            print(f"  [Detect] Loading 检测失败: {e}")
        
        return result
    
    def detect_native_error_toast(self) -> Dict[str, Any]:
        """检测页面是否有原生错误提示组件
        
        策略：
        1. 检测是否有 toast/snackbar/notification 组件
        2. 检测是否有可以触发的错误提示机制
        """
        result = {
            'has_native_toast': False,
            'toast_selectors': [],
            'can_trigger_native': False,
            'trigger_method': None,
        }
        
        try:
            # 方法1：检测现有的 toast 元素
            for selector in self.ERROR_TOAST_SELECTORS:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        result['has_native_toast'] = True
                        result['toast_selectors'].append(selector)
                except:
                    continue
            
            # 方法2：检测是否有可以触发的 toast 服务
            native_toast_check = self.driver.execute_script("""
                // Angular Material Snackbar
                if (window.ng) {
                    const injector = window.ng.getInjector && window.ng.getInjector(document.body);
                    if (injector) {
                        try {
                            // Angular 有 MatSnackBar 服务
                            return { framework: 'angular-material', available: true };
                        } catch(e) {}
                    }
                }
                // 检测 Toastr
                if (window.toastr) {
                    return { framework: 'toastr', available: true };
                }
                // 检测 SweetAlert
                if (window.Swal || window.swal) {
                    return { framework: 'sweetalert', available: true };
                }
                // 检测 Vue 的 Element UI / Vuetify
                if (window.Vue) {
                    if (window.ELEMENT && window.ELEMENT.Message) {
                        return { framework: 'element-ui', available: true };
                    }
                }
                // 检测 React Toastify
                if (window.ReactToastify) {
                    return { framework: 'react-toastify', available: true };
                }
                return { available: false };
            """)
            
            if native_toast_check and native_toast_check.get('available'):
                result['can_trigger_native'] = True
                result['trigger_method'] = native_toast_check.get('framework')
                print(f"  [Detect] 发现原生 Toast 机制: {native_toast_check.get('framework')}")
                
        except Exception as e:
            print(f"  [Detect] Toast 检测失败: {e}")
        
        return result
    
    def trigger_native_error_toast(self, error_message: str = "Server Error (500)") -> bool:
        """尝试触发原生的错误提示
        
        Returns:
            bool: 是否成功触发原生 toast
        """
        try:
            result = self.driver.execute_script("""
                const errorMsg = arguments[0];
                
                // 方法1: Angular Material Snackbar
                if (window.ng) {
                    try {
                        const appRef = window.ng.getComponent(document.querySelector('[ng-version]'));
                        if (appRef) {
                            // 尝试注入错误
                            const event = new CustomEvent('http-error', { detail: { status: 500, message: errorMsg } });
                            document.dispatchEvent(event);
                            return { triggered: true, method: 'angular-event' };
                        }
                    } catch(e) {}
                }
                
                // 方法2: Toastr
                if (window.toastr) {
                    toastr.error(errorMsg, 'Error');
                    return { triggered: true, method: 'toastr' };
                }
                
                // 方法3: SweetAlert
                if (window.Swal) {
                    Swal.fire({ icon: 'error', title: 'Error', text: errorMsg });
                    return { triggered: true, method: 'sweetalert' };
                }
                
                // 方法4: Element UI
                if (window.ELEMENT && window.ELEMENT.Message) {
                    window.ELEMENT.Message.error(errorMsg);
                    return { triggered: true, method: 'element-ui' };
                }
                
                return { triggered: false };
            """, error_message)
            
            if result and result.get('triggered'):
                print(f"  [Trigger] 原生 Toast 触发成功: {result.get('method')}")
                return True
                
        except Exception as e:
            print(f"  [Trigger] 原生 Toast 触发失败: {e}")
        
        return False
    
    def trigger_native_loading(self) -> bool:
        """尝试触发原生的 loading spinner
        
        Returns:
            bool: 是否成功触发原生 loading
        """
        try:
            result = self.driver.execute_script("""
                // 方法1: 显示隐藏的 loading overlay
                const hiddenLoaders = document.querySelectorAll(
                    '[class*="loading"][style*="display: none"], ' +
                    '[class*="spinner"][style*="display: none"], ' +
                    '[class*="overlay"][style*="visibility: hidden"], ' +
                    '.mat-progress-spinner, .mat-progress-bar, ' +
                    '.ngx-spinner, .v-progress-circular'
                );
                
                for (const loader of hiddenLoaders) {
                    loader.style.display = 'flex';
                    loader.style.visibility = 'visible';
                    loader.style.opacity = '1';
                    loader.style.position = 'fixed';
                    loader.style.top = '0';
                    loader.style.left = '0';
                    loader.style.width = '100%';
                    loader.style.height = '100%';
                    loader.style.zIndex = '99999';
                    loader.style.backgroundColor = 'rgba(0,0,0,0.5)';
                    return { triggered: true, method: 'show-hidden', selector: loader.className };
                }
                
                // 方法2: 触发 ngx-spinner
                if (window.NgxSpinnerService) {
                    // 无法直接访问服务，但可以触发事件
                    document.dispatchEvent(new CustomEvent('spinner-show'));
                    return { triggered: true, method: 'ngx-spinner-event' };
                }
                
                return { triggered: false };
            """)
            
            if result and result.get('triggered'):
                print(f"  [Trigger] 原生 Loading 触发成功: {result.get('method')}")
                return True
                
        except Exception as e:
            print(f"  [Trigger] 原生 Loading 触发失败: {e}")
        
        return False
    

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
        self.native_detector = NativeErrorPageDetector(self.driver)  # 🆕 原生错误页面检测器
        self._native_404_cache: Dict[str, str | None] = {}  # 缓存每个域名的原生 404 URL

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
        """智能填充表单字段，使 disabled 按钮变为可用状态。"""
        filled_count = 0
        # 字段类型 → 默认值
        samples = {
            "text": "testuser", "email": "test@example.com", "password": "TestPass123!",
            "search": "test", "tel": "1234567890", "number": "42",
        }
        # 字段名关键词 → 值
        hints = {
            "email": "test@example.com", "mail": "test@example.com",
            "password": "TestPass123!", "pass": "TestPass123!", "confirm": "TestPass123!",
            "name": "Test User", "phone": "1234567890", "comment": "Test comment.",
        }
        
        try:
            # 1. 填充 input/textarea
            for f in self.driver.find_elements(By.CSS_SELECTOR,
                "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='checkbox']):not([type='radio']):not([type='file']), textarea"):
                try:
                    if not f.is_displayed() or (f.get_attribute("value") or "").strip():
                        continue
                    ftype = (f.get_attribute("type") or "text").lower()
                    ctx = f"{f.get_attribute('name') or ''} {f.get_attribute('id') or ''} {f.get_attribute('placeholder') or ''}".lower()
                    sample = next((v for k, v in hints.items() if k in ctx), samples.get(ftype, "test"))
                    f.clear()
                    f.send_keys(sample)
                    filled_count += 1
                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('input',{bubbles:true}));arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", f)
                except: continue
            
            # 2. 勾选复选框
            for cb in self.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox'], mat-checkbox"):
                try:
                    if cb.is_displayed() and not (cb.get_attribute("checked") or cb.get_attribute("aria-checked") == "true"):
                        cb.click()
                except: continue
            
            # 3. 选择下拉框第一项
            for ms in self.driver.find_elements(By.CSS_SELECTOR, "mat-select"):
                try:
                    if ms.is_displayed() and not ms.text.strip():
                        ms.click()
                        time.sleep(0.2)
                        opts = self.driver.find_elements(By.CSS_SELECTOR, "mat-option")
                        if opts:
                            for o in opts:
                                if o.is_displayed(): o.click(); break
                except: continue
            
            if filled_count > 0:
                print(f"  [Prefill] Filled {filled_count} form field(s)")
        except: pass

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
        """注入 Operation_No_Response bug（包含两种子类型）
        
        Big Three Taxonomy - Type B:
        - Sub-variant 1 (Dead Click): 阻止所有事件 + 网络拦截，点击无反应
        - Sub-variant 2 (Timeout Hang): 显示 Loading Spinner 遮罩
        
        🆕 智能策略：
        1. 优先尝试触发网站原生的 Loading Spinner
        2. 如果没有原生 Loading → 使用注入样式 (5种随机选择)
        """
        injection_success = False
        used_native = False
        loading_source = "injected"
        
        # 随机选择子类型：50% Dead Click, 50% Timeout Hang
        sub_variant = random.choice(["dead_click", "timeout_hang"])
        
        # 🆕 关键修复：在点击前阻止元素的所有事件处理
        try:
            self.driver.execute_script("""
                (function(el) {
                    // 方法1：移除所有事件监听器（克隆替换）
                    const clone = el.cloneNode(true);
                    if (el.parentNode) {
                        el.parentNode.replaceChild(clone, el);
                    }
                    
                    // 方法2：阻止所有事件
                    const blockEvents = ['click', 'mousedown', 'mouseup', 'touchstart', 'touchend', 'submit'];
                    blockEvents.forEach(evt => {
                        clone.addEventListener(evt, function(e) {
                            e.preventDefault();
                            e.stopPropagation();
                            e.stopImmediatePropagation();
                            console.log('[ICE] Event blocked:', evt);
                            return false;
                        }, true);
                    });
                    
                    // 视觉标记
                    clone.style.outline = '3px solid #ff6b6b';
                    clone.style.opacity = '0.6';
                    clone.style.cursor = 'not-allowed';
                    
                    console.log('[ICE] Element events blocked for Operation_No_Response');
                })(arguments[0]);
            """, element)
            injection_success = True
        except Exception as e:
            print(f"  [Inject] Operation_No_Response: ✗ Event blocking failed - {e}")
        
        # 网络拦截（作为额外保障）
        if self.use_js_interceptor:
            self.js_interceptor.inject_fetch_interceptor()
            self.js_interceptor.reset_interceptor()
            self.js_interceptor.clear_logs()
            self.js_interceptor.intercept_request_timeout(r'.*')
        
        # Sub-variant 2: Timeout Hang - 显示 Loading Spinner
        if sub_variant == "timeout_hang":
            # 🆕 优先尝试原生 Loading
            native_loading = self.native_detector.detect_native_loading()
            if native_loading.get('can_trigger_native'):
                if self.native_detector.trigger_native_loading():
                    used_native = True
                    loading_source = f"native ({native_loading.get('trigger_method')})"
                    print(f"  [Inject] Operation_No_Response: ✓ Using NATIVE Loading")
                    injection_success = True
            
            # 没有原生或触发失败，使用注入样式
            if not used_native:
                loading_style = get_random_loading_style()
                try:
                    js_code = generate_loading_overlay_js(loading_style)
                    self.driver.execute_script(js_code)
                    loading_source = f"style: {loading_style['name']}"
                    print(f"  [Inject] Operation_No_Response ({sub_variant}): ✓ Overlay injected ({loading_source})")
                    injection_success = True
                except Exception as e:
                    print(f"  [Inject] Operation_No_Response ({sub_variant}): ✗ Overlay failed - {e}")
        
        status = "✓ Injected" if injection_success else "✗ Failed"
        desc_suffix = f"(loading: {loading_source})" if sub_variant == "timeout_hang" else "(dead click)"
        print(f"  [Inject] Operation_No_Response: {status} {desc_suffix}")
        
        return "Operation_No_Response", f"Click initiated request but network was intercepted; no response received {desc_suffix}."

    def inject_navigation_error(self, element):
        """注入 Navigation_Error bug
        
        Big Three Taxonomy - Type A:
        - 用户点击后被重定向到 404 页面/白屏/错误路由
        
        🆕 智能策略:
        1. 首先检查缓存中是否有原生 404 页面信息
        2. 如果有原生 404 → 直接导航到原生 404 (更真实、更多样)
        3. 如果没有 → 使用注入样式 (随机选择5种样式之一)
        
        注意：为避免 stale element，我们先点击元素，再进行 404 检测/导航
        """
        # 清除之前的拦截配置
        if self.use_js_interceptor:
            self.js_interceptor.reset_interceptor()
            self.js_interceptor.clear_logs()
        
        current_url = self.driver.current_url
        base_url = '/'.join(current_url.split('/')[:3])
        
        try:
            # 劫持 pushState (SPA)
            self.driver.execute_script("""
                const orig_pushState = window.history.pushState;
                window.history.pushState = function(...args) {
                    console.log('[ICE] Navigation hijacked via pushState');
                    args[2] = '/nonexistent-page-' + Math.random().toString(36).substr(2, 9);
                    return orig_pushState.apply(this, args);
                };
                window.__ICE_NAV_ERROR__ = true;
            """)
            print("  [Inject] Navigation_Error: ✓ Injected")
        except Exception as e:
            print(f"  [Inject] Navigation_Error: ✗ Failed - {e}")
        
        # 🔥 先点击元素，再进行导航（避免 stale element）
        try:
            element.click()
        except Exception:
            try:
                self.driver.execute_script("arguments[0].click();", element)
            except:
                pass
        
        # 等待
        time.sleep(0.3)
        
        # 🆕 检测原生 404 页面（点击后检测，元素已不重要）
        native_404_result = self.native_detector.detect_native_404(base_url)
        use_native = native_404_result['has_native_404']
        native_404_url = native_404_result.get('native_404_url')
        
        if use_native and native_404_url:
            # 🆕 使用网站原生 404 页面
            try:
                self.driver.get(native_404_url)
                print(f"  [Inject] Navigation_Error: → Using NATIVE 404: {native_404_url}")
                time.sleep(0.5)
                return "Navigation_Error", f"Navigation hijacked; native 404 page displayed ({native_404_url})."
            except Exception as e:
                print(f"  [Inject] Navigation_Error: ✗ Native 404 failed - {e}, falling back to injected style")
                use_native = False
        
        # 没有原生 404 或原生导航失败，使用注入样式
        if not use_native:
            style_404 = get_random_404_style()
            try:
                error_path = f"{base_url}/error-404-page-not-found-{random.randint(1000, 9999)}"
                self.driver.get(error_path)
                print(f"  [Inject] Navigation_Error: → Navigated to {error_path}")
                
                # 注入多样化 404 页面内容
                time.sleep(0.5)
                js_code = generate_404_page_js(style_404)
                self.driver.execute_script(js_code)
                print(f"  [Inject] Navigation_Error: ✓ 404 page injected (style: {style_404['name']})")
                return "Navigation_Error", f"Navigation hijacked; 404 page displayed (style: {style_404['name']})."
            except Exception as e:
                print(f"  [Inject] Navigation_Error: ✗ Failed to navigate - {e}")
        
        return "Navigation_Error", "Navigation hijacked; error page displayed."

    def inject_unexpected_feedback(self, element):
        """注入 Unexpected_Task_Result bug
        
        Big Three Taxonomy - Type C:
        - 用户点击后系统返回可见错误 (500 Error Toast)
        
        🆕 智能策略：
        1. 优先尝试触发网站原生的 Error Toast/Notification
        2. 如果没有原生 → 使用注入样式 (5种随机选择)
        """
        injection_success = False
        used_native = False
        toast_source = "injected"
        
        # 网络拦截返回 500
        if self.use_js_interceptor:
            self.js_interceptor.inject_fetch_interceptor()
            self.js_interceptor.reset_interceptor()
            self.js_interceptor.clear_logs()
            injection_success = self.js_interceptor.intercept_request_error(r'.*', error_code=500)
        
        # 🆕 优先尝试原生 Error Toast
        native_toast = self.native_detector.detect_native_error_toast()
        if native_toast.get('can_trigger_native'):
            if self.native_detector.trigger_native_error_toast("Server Error: 500 Internal Server Error"):
                used_native = True
                toast_source = f"native ({native_toast.get('trigger_method')})"
                print(f"  [Inject] Unexpected_Task_Result: ✓ Using NATIVE Toast")
                injection_success = True
        
        # 没有原生或触发失败，使用注入样式
        if not used_native:
            error_style = get_random_error_toast_style()
            try:
                js_code = generate_error_toast_js(error_style)
                self.driver.execute_script(js_code)
                toast_source = f"style: {error_style['name']}"
                print(f"  [Inject] Unexpected_Task_Result: ✓ Error Toast injected ({toast_source})")
                injection_success = True
            except Exception as e:
                print(f"  [Inject] Unexpected_Task_Result: ✗ Toast injection failed - {e}")
        
        status = "✓ Injected" if injection_success else "✗ Failed"
        print(f"  [Inject] Unexpected_Task_Result: {status}")
        return "Unexpected_Task_Result", f"API returned 500 error; error toast displayed ({toast_source})."

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

        return {"visual_verified": bool(visual_ok), "signals": signals}

    def _calculate_visual_diff(self, img_path1: str, img_path2: str) -> Dict[str, Any]:
        """
        计算两张截图的视觉差异。
        返回包含差异度量的字典。
        """
        result = {
            "has_diff": False,
            "diff_percentage": 0.0,
            "diff_score": 0.0,
            "method": "none",
            "error": None
        }
        
        if not os.path.exists(img_path1) or not os.path.exists(img_path2):
            result["error"] = "Image files not found"
            return result
        
        try:
            # 优先使用 OpenCV（更精确）
            if HAS_CV2:
                img1 = cv2.imread(img_path1)
                img2 = cv2.imread(img_path2)
                
                if img1 is None or img2 is None:
                    result["error"] = "Failed to load images with cv2"
                    return result
                
                # 确保尺寸一致
                if img1.shape != img2.shape:
                    img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
                
                # 计算结构相似度 (SSIM)
                gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
                ssim_score = ssim(gray1, gray2)
                
                # 计算像素差异百分比
                diff = cv2.absdiff(img1, img2)
                non_zero = np.count_nonzero(diff)
                total_pixels = img1.shape[0] * img1.shape[1] * img1.shape[2]
                diff_percentage = (non_zero / total_pixels) * 100
                
                result["method"] = "opencv_ssim"
                result["diff_score"] = float(round(1.0 - ssim_score, 4))  # 转换为差异分数
                result["diff_percentage"] = float(round(diff_percentage, 2))
                # 如果 SSIM 差异 > 0.05 或像素差异 > 2%，认为有明显变化
                result["has_diff"] = bool((1.0 - ssim_score) > 0.05 or diff_percentage > 2.0)
                
            # 回退到 PIL（更基础）
            elif HAS_PIL:
                img1 = Image.open(img_path1)
                img2 = Image.open(img_path2)
                
                # 确保尺寸一致
                if img1.size != img2.size:
                    img2 = img2.resize(img1.size)
                
                # 计算像素差异
                diff = ImageChops.difference(img1, img2)
                diff_array = np.array(diff)
                non_zero = np.count_nonzero(diff_array)
                total_pixels = diff_array.size
                diff_percentage = (non_zero / total_pixels) * 100
                
                result["method"] = "pil_pixel_diff"
                result["diff_percentage"] = float(round(diff_percentage, 2))
                # PIL 阈值：像素差异 > 5%
                result["has_diff"] = bool(diff_percentage > 5.0)
                
            else:
                result["error"] = "No image comparison library available (install opencv-python or pillow)"
                
        except Exception as e:
            result["error"] = f"Diff calculation failed: {str(e)}"
        
        return result

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
        normal_click_captured = False
        reference_path = ""

        # Big Three Bug Taxonomy mapping
        bug_name_mapping = {
            "Navigation_Error": "nav_error",
            "Operation_No_Response": "no_response",
            "Unexpected_Task_Result": "fake_error",
        }
        display_name_from_key = {
            "nav_error": "Navigation_Error",
            "no_response": "Operation_No_Response",
            "fake_error": "Unexpected_Task_Result",
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
            
            # 🆕 保存元素选择器，用于后续重新定位
            element_selector = {
                "id": elem_info.get("id", ""),
                "text": elem_info.get("text", "")[:30] if elem_info.get("text") else "",
                "css_selector": f"{elem_info.get('tag', 'button')}#{elem_info.get('id')}" if elem_info.get("id") else "",
            }
            
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
            
            # 🆕 Visual Diff 策略：比较「点击前」vs「点击后」
            # - Navigation_Error/Unexpected_Task_Result：期望有视觉变化
            # - Operation_No_Response：期望没有视觉变化（页面冻结）或有 Loading Spinner
            pre_click_screenshot_path = t1_path.replace("_end.png", "_pre_click.png")
            pre_click_captured = False
            
            print(f"  [Visual Diff] Capturing pre-click state...")
            try:
                # 截取点击前的状态
                self.driver.save_screenshot(pre_click_screenshot_path)
                pre_click_captured = True
                print(f"  [✓] Pre-click screenshot captured")
            except Exception as e:
                print(f"  [!] Failed to capture pre-click screenshot: {e}")

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
            else:
                # Fallback to Navigation_Error if unknown key
                bug_type, desc = self.inject_navigation_error(element)
            
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

                # 🆕 计算视觉 Diff（对比「点击前」vs「点击后」）
                visual_diff_result = {}
                visual_diff_verified = False
                
                if pre_click_captured and os.path.exists(pre_click_screenshot_path):
                    print(f"  [Visual Diff] Comparing pre-click vs post-click state...")
                    try:
                        # 计算两张截图的差异（点击前 vs 点击后）
                        # 对于 end screenshot，需要使用没有红标的版本
                        t1_clean_path = t1_path.replace("_end.png", "_end_clean.png")
                        self.driver.save_screenshot(t1_clean_path)
                        
                        visual_diff_result = self._calculate_visual_diff(pre_click_screenshot_path, t1_clean_path)
                        has_visual_change = visual_diff_result.get("has_diff", False)
                        diff_pct = visual_diff_result.get("diff_percentage", 0)
                        
                        # 🎯 根据 bug 类型决定验证逻辑
                        if bug_type == "Operation_No_Response":
                            # Operation_No_Response：期望页面冻结，即没有视觉变化
                            # 如果像素差异 < 1%，则验证成功（页面确实冻结了）
                            visual_diff_verified = bool(diff_pct < 1.0)
                            if visual_diff_verified:
                                print(f"  [✓ Visual Diff] Page frozen confirmed: only {diff_pct:.2f}% change (expected < 1%)")
                            else:
                                print(f"  [✗ Visual Diff] Page not frozen: {diff_pct:.2f}% change (expected < 1%)")
                        else:
                            # 其他 bug 类型：期望有明显视觉变化（错误页面、错误消息等）
                            visual_diff_verified = bool(has_visual_change)
                            if visual_diff_verified:
                                print(f"  [✓ Visual Diff] Visual change detected: {diff_pct:.2f}% pixels changed")
                            else:
                                print(f"  [✗ Visual Diff] No significant visual change: {diff_pct:.2f}%")
                        
                        visual_diff_result["expected_behavior"] = "no_change" if bug_type == "Operation_No_Response" else "change"
                        visual_diff_result["verified"] = bool(visual_diff_verified)
                        
                        # 清理临时截图
                        try:
                            os.remove(pre_click_screenshot_path)
                            os.remove(t1_clean_path)
                        except:
                            pass
                    except Exception as e:
                        print(f"  [!] Visual diff calculation failed: {e}")
                        visual_diff_result = {"error": str(e)}
                else:
                    visual_diff_result = {"error": "Pre-click screenshot not captured"}
                    print(f"  [!] Skipping visual diff (no pre-click screenshot)")

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
                
                # 🆕 综合判定逻辑：加入视觉 diff 作为强证据
                injection_verified = False
                if visual_diff_verified:
                    # 视觉 diff 作为最强证据：如果检测到明显视觉变化，直接验证通过
                    injection_verified = True
                    print(f"  [✓ Verification] Verified by visual diff (strongest evidence)")
                elif bug_type == "Navigation_Error":
                    # Navigation_Error 依赖 DOM 变化（URL 跳转到 404）
                    injection_verified = visual_verified or has_network_logs
                elif has_network_logs:
                    # 有网络日志即验证通过
                    injection_verified = True
                else:
                    # 回退到视觉验证
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
                    "visual_diff": visual_diff_result,  # 🆕 新增视觉 diff 结果
                    "visual_diff_verified": visual_diff_verified,  # 🆕 视觉 diff 是否验证通过
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
