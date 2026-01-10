import random
import re
from urllib.parse import urlparse
from typing import List, Set
from selenium.webdriver.common.by import By

from .config import LINK_DISCOVERY_LIMIT


def get_candidates(driver, prioritize_network=True) -> List:
    """获取可交互元素，优先选择会触发网络请求的元素"""
    # 高优先级：通常会触发网络请求的元素（权重3）
    high_priority_selectors = [
        # 表单提交
        "button[type='submit']",
        "input[type='submit']",
        "form button",
        "button[class*='submit']",
        # Angular Material 表单按钮
        "[mat-raised-button]",
        "[mat-flat-button]",
        "button[mat-button]",
        # 功能按钮
        "button[class*='search']",
        "button[class*='login']",
        "button[class*='register']",
        "button[class*='add']",
        "button[class*='save']",
        "button[class*='delete']",
        "button[class*='confirm']",
        "button[class*='buy']",
        "button[class*='checkout']",
        "button[class*='order']",
        "button[class*='send']",
        "button[class*='post']",
        # 导航到表单的链接
        "a[href*='login']",
        "a[href*='register']",
        "a[href*='checkout']",
        "a[href*='cart']",
        # 有data属性的交互元素
        "[data-action]",
        "[onclick*='fetch']",
        "[onclick*='ajax']",
        "[onclick*='submit']",
    ]
    
    # 中优先级：可能触发请求的元素（权重2）
    medium_priority_selectors = [
        "button:not([type='button'])",  # 默认type="submit"
        "[role='button']",
        "button[class*='btn']",
        "a[class*='btn']",
        # Angular Material 图标按钮
        "[mat-icon-button]",
    ]
    
    # 低优先级：可点击链接
    low_priority_selectors = [
        "a[href]:not([href='#']):not([href='javascript:void(0)']):not([href^='mailto'])",
    ]
    
    # 收集元素并标记优先级
    high_elems = []
    medium_elems = []
    low_elems = []
    seen_ids = set()  # 去重
    
    def add_unique(elem, target_list):
        """去重添加元素"""
        try:
            elem_id = id(elem)
            if elem_id not in seen_ids:
                seen_ids.add(elem_id)
                target_list.append(elem)
        except:
            pass
    
    for sel in high_priority_selectors:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                add_unique(el, high_elems)
        except Exception:
            continue
    
    for sel in medium_priority_selectors:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                add_unique(el, medium_elems)
        except Exception:
            continue
    
    for sel in low_priority_selectors:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                add_unique(el, low_elems)
        except Exception:
            continue
    
    # 合并（高优先级在前）
    all_elems = high_elems + medium_elems + low_elems
    
    candidates = []
    for el in all_elems:
        # 允许 disabled 的提交按钮（我们可以先填充表单）
        if not _is_valid_candidate(driver, el, allow_disabled_submit=True):
            continue
        candidates.append(el)
    
    # 如果优先选择网络元素，将高优先级元素放前面（已经是了）
    # 打乱时保持优先级分组
    if prioritize_network and len(candidates) > 10:
        # 前50%保持原顺序（高优先级），后50%打乱
        mid = len(candidates) // 2
        tail = candidates[mid:]
        random.shuffle(tail)
        candidates = candidates[:mid] + tail
    
    return candidates


def get_network_triggering_candidates(driver) -> List:
    """专门获取会触发网络请求的元素，用于网络类Bug注入"""
    # 最可能触发网络请求的选择器
    network_selectors = [
        # 表单提交
        "button[type='submit']",
        "input[type='submit']",
        "form button:not([type='button'])",
        # Angular Material 表单按钮
        "[mat-raised-button]",
        "[mat-flat-button]",
        "button[mat-button]",
        # 登录/注册
        "button[class*='login']",
        "button[class*='sign']",
        "button[class*='register']",
        # 购物/交易
        "button[class*='add-to-cart']",
        "button[class*='buy']",
        "button[class*='checkout']",
        "button[class*='order']",
        "button[class*='purchase']",
        # 搜索
        "button[class*='search']",
        "input[type='search'] ~ button",
        # 数据操作
        "button[class*='save']",
        "button[class*='delete']",
        "button[class*='update']",
        "button[class*='send']",
        "button[class*='post']",
        "button[class*='submit']",
        # API触发
        "[data-action]",
        "[onclick*='fetch']",
        "[onclick*='ajax']",
        "[onclick*='http']",
        "[onclick*='api']",
        # 有明确文本暗示的按钮
        "button",  # 会在后面过滤
    ]
    
    seen_ids = set()
    candidates = []
    
    for sel in network_selectors:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                elem_id = id(el)
                if elem_id in seen_ids:
                    continue
                seen_ids.add(elem_id)
                
                # 允许 disabled 的提交按钮
                if not _is_valid_candidate(driver, el, allow_disabled_submit=True):
                    continue
                
                # 额外过滤：排除明显不触发网络的按钮
                text = (el.text or "").strip().lower()
                aria_label = (el.get_attribute("aria-label") or "").lower()
                elem_class = (el.get_attribute("class") or "").lower()
                
                # 排除：切换、显示/隐藏、菜单等UI交互
                skip_keywords = [
                    "toggle", "show", "hide", "display", "password",
                    "menu", "dropdown", "collapse", "expand", "close",
                    "dismiss", "cancel", "back", "previous", "next",
                    "language", "theme", "dark", "light",
                    # 新增：排除外部OAuth登录（会跳转到外部网站）
                    "google", "facebook", "twitter", "github", "oauth",
                    "sign in with", "log in with", "continue with"
                ]
                
                should_skip = False
                for kw in skip_keywords:
                    if kw in text or kw in aria_label or kw in elem_class:
                        should_skip = True
                        break
                
                if should_skip:
                    continue
                
                # 优先：有明确网络操作暗示的文本
                action_keywords = [
                    "submit", "login", "sign", "register", "send",
                    "save", "add", "buy", "order", "checkout", "pay",
                    "search", "delete", "update", "post", "confirm"
                ]
                
                has_action_hint = any(
                    kw in text or kw in aria_label or kw in elem_class
                    for kw in action_keywords
                )
                
                if has_action_hint:
                    candidates.insert(0, el)  # 高优先级放前面
                else:
                    candidates.append(el)
        except Exception:
            continue
    
    return candidates


def _is_valid_candidate(driver, el, allow_disabled_submit=False) -> bool:
    """检查元素是否是有效的候选
    
    Args:
        driver: Selenium WebDriver
        el: 要检查的元素
        allow_disabled_submit: 是否允许 disabled 的提交按钮（用于表单场景）
    """
    try:
        # 基本可见性检查
        if not el.is_displayed():
            return False
        
        # 检查是否是提交按钮
        is_submit_button = False
        aria_label = (el.get_attribute("aria-label") or "").lower()
        elem_text = (el.text or "").strip().lower()
        elem_class = (el.get_attribute("class") or "").lower()
        elem_type = (el.get_attribute("type") or "").lower()
        
        submit_keywords = ["submit", "login", "log in", "sign in", "register", 
                          "send", "save", "confirm", "checkout", "buy", "order"]
        if any(kw in aria_label or kw in elem_text or kw in elem_class for kw in submit_keywords):
            is_submit_button = True
        if elem_type == "submit":
            is_submit_button = True
        if el.get_attribute("mat-raised-button") is not None:
            # mat-raised-button 通常是主要操作按钮
            is_submit_button = True
        
        # 如果是 disabled 元素
        if not el.is_enabled():
            # 只有当 allow_disabled_submit=True 且是提交按钮时才允许
            if not (allow_disabled_submit and is_submit_button):
                return False
        
        tag = el.tag_name.lower()
        
        # 1. 排除图片元素
        if tag == "img":
            return False
        
        # 2. 排除纯展示性的span/div
        if tag in ("span", "div"):
            has_interaction = False
            for attr in ["onclick", "role", "data-action", "ng-click", "@click", "v-on:click"]:
                if el.get_attribute(attr):
                    has_interaction = True
                    break
            if not has_interaction:
                return False
        
        # 获取元素属性
        elem_id = (el.get_attribute("id") or "").lower()
        
        # 3. 排除导航logo/品牌链接
        if any(kw in elem_class for kw in ["logo", "brand", "navbar-brand"]):
            return False
        
        # 4. 排除语言切换器、菜单按钮等辅助功能
        skip_labels = ["language", "theme", "dark mode", "accessibility", 
                       "open menu", "close menu", "toggle menu"]
        if any(kw in aria_label for kw in skip_labels):
            return False
        # 排除只显示"menu"文本的按钮
        if elem_text == "menu":
            return False
        
        # 5. 排除外部OAuth登录按钮（会跳转到外部网站）
        oauth_keywords = ["google", "facebook", "twitter", "github", "oauth",
                          "sign in with", "log in with", "continue with", "linkedin"]
        combined_text = f"{elem_text} {aria_label} {elem_class}"
        if any(kw in combined_text for kw in oauth_keywords):
            return False
        
        # 6. 排除网站 Logo/标题按钮 (通常只会导航回主页)
        site_name_keywords = ["owasp", "juice shop", "juice-shop"]
        if any(kw in elem_text for kw in site_name_keywords):
            return False
        
        # 7. 排除导航栏内的纯导航按钮
        # 检查是否是 mat-toolbar 内的按钮（Angular Material顶部工具栏）
        in_top_toolbar = driver.execute_script("""
            const el = arguments[0];
            let p = el.parentElement;
            let depth = 0;
            while (p && depth < 5) {
                const tag = p.tagName.toLowerCase();
                const cls = (p.className || '').toLowerCase();
                // 只检查顶部工具栏（mat-toolbar）
                if (cls.includes('mat-toolbar') && !cls.includes('mat-toolbar-row')) {
                    return true;
                }
                // 如果遇到主内容区域，停止检查
                if (cls.includes('mat-sidenav-content') || cls.includes('main-content') || 
                    tag === 'main' || cls.includes('page-content')) {
                    return false;
                }
                p = p.parentElement;
                depth++;
            }
            return false;
        """, el)
        
        if in_top_toolbar:
            # 在顶部工具栏内，排除 Account 等打开菜单的按钮
            skip_toolbar_keywords = ["account", "menu", "language"]
            if any(kw in combined_text for kw in skip_toolbar_keywords):
                return False
        
        # 8. CSS可见性检查
        style = driver.execute_script(
            """
            const el = arguments[0];
            const s = getComputedStyle(el);
            return {
              display: s.display,
              visibility: s.visibility,
              opacity: parseFloat(s.opacity || '1'),
              pointerEvents: s.pointerEvents,
              ariaHidden: el.getAttribute('aria-hidden') || ''
            };
            """,
            el,
        )
        if style.get("display") == "none" or style.get("visibility") == "hidden":
            return False
        # 对于提交按钮，放宽 pointer-events 限制（disabled按钮通常有 pointer-events: none）
        if style.get("pointerEvents") == "none":
            if not (allow_disabled_submit and is_submit_button):
                return False
        if style.get("opacity", 1) is not None and style.get("opacity", 1) < 0.2:
            return False
        if style.get("ariaHidden", "").lower() == "true":
            return False

        # 9. 尺寸检查
        rect = el.rect
        if rect.get("width", 0) < 24 or rect.get("height", 0) < 24:
            return False
        
        return True
    except Exception:
        return False


def discover_internal_links(driver, base_url: str, limit: int = LINK_DISCOVERY_LIMIT) -> List[str]:
    try:
        parsed_base = urlparse(base_url)
        anchors = driver.find_elements(By.TAG_NAME, "a")
        seen: Set[str] = set()
        links: List[str] = []
        for a in anchors:
            href = a.get_attribute("href")
            if not href:
                continue
            parsed = urlparse(href)
            if parsed.scheme not in ("http", "https"):
                continue
            if parsed.netloc != parsed_base.netloc:
                continue
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if normalized in seen:
                continue
            seen.add(normalized)
            links.append(normalized)
            if len(links) >= limit:
                break
        if links:
            print(f"[*] Discovered {len(links)} internal links on {parsed_base.netloc}")
        return links
    except Exception as e:
        print(f"[!] Link discovery failed: {e}")
        return []
