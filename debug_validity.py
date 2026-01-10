#!/usr/bin/env python3
"""调试_is_valid_candidate的每个条件"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

options = Options()
options.add_argument('--headless')
driver = webdriver.Chrome(options=options)

try:
    driver.get('http://localhost:3000/#/login')
    time.sleep(2)

    # 找到登录按钮
    raised = driver.find_elements(By.CSS_SELECTOR, '[mat-raised-button]')
    el = raised[0]  # exit_to_app Log in

    print("Testing element:", el.text.strip().replace('\n', ' ')[:40])
    print()

    # 基本可见性检查
    if not el.is_displayed():
        print('FAIL: not displayed')
    else:
        print('PASS: displayed')

    # 检查是否是提交按钮
    is_submit_button = False
    aria_label = (el.get_attribute('aria-label') or '').lower()
    elem_text = (el.text or '').strip().lower()
    elem_class = (el.get_attribute('class') or '').lower()
    elem_type = (el.get_attribute('type') or '').lower()

    submit_keywords = ['submit', 'login', 'log in', 'sign in', 'register', 
                      'send', 'save', 'confirm', 'checkout', 'buy', 'order']
    if any(kw in aria_label or kw in elem_text or kw in elem_class for kw in submit_keywords):
        is_submit_button = True
    if elem_type == 'submit':
        is_submit_button = True
    if el.get_attribute('mat-raised-button') is not None:
        is_submit_button = True
    print(f'is_submit_button: {is_submit_button}')

    # 如果是 disabled 元素
    if not el.is_enabled():
        print(f'Element is disabled, is_submit_button={is_submit_button}')
        if is_submit_button:
            print('PASS: disabled but allowed (submit button)')
        else:
            print('FAIL: disabled and not submit button')
    else:
        print('PASS: enabled')

    tag = el.tag_name.lower()
    print(f'tag: {tag}')

    # 排除图片
    if tag == 'img':
        print('FAIL: img')

    # 排除 logo/brand
    if any(kw in elem_class for kw in ['logo', 'brand', 'navbar-brand']):
        print('FAIL: logo/brand')
    else:
        print('PASS: not logo/brand')

    # skip_labels
    skip_labels = ['language', 'theme', 'dark mode', 'accessibility', 
                   'open menu', 'close menu', 'toggle menu']
    if any(kw in aria_label for kw in skip_labels):
        print(f'FAIL: skip_label in aria')
    elif elem_text == 'menu':
        print('FAIL: text is menu')
    else:
        print('PASS: not skip_labels')

    # OAuth
    oauth_keywords = ['google', 'facebook', 'twitter', 'github', 'oauth',
                      'sign in with', 'log in with', 'continue with', 'linkedin']
    combined_text = f'{elem_text} {aria_label} {elem_class}'
    matched_oauth = [kw for kw in oauth_keywords if kw in combined_text]
    if matched_oauth:
        print(f'FAIL: OAuth keyword: {matched_oauth}')
    else:
        print('PASS: not OAuth')

    # site name
    site_name_keywords = ['owasp', 'juice shop', 'juice-shop']
    if any(kw in elem_text for kw in site_name_keywords):
        print('FAIL: site name')
    else:
        print('PASS: not site name')

    # toolbar
    in_top_toolbar = driver.execute_script("""
        const el = arguments[0];
        let p = el.parentElement;
        let depth = 0;
        while (p && depth < 5) {
            const cls = (p.className || "").toLowerCase();
            if (cls.includes("mat-toolbar") && !cls.includes("mat-toolbar-row")) {
                return true;
            }
            if (cls.includes("mat-sidenav-content") || cls.includes("main-content") || 
                p.tagName.toLowerCase() === "main" || cls.includes("page-content")) {
                return false;
            }
            p = p.parentElement;
            depth++;
        }
        return false;
    """, el)
    print(f'in_top_toolbar: {in_top_toolbar}')

    if in_top_toolbar:
        skip_toolbar_keywords = ['account', 'menu', 'language']
        matched = [kw for kw in skip_toolbar_keywords if kw in combined_text]
        if matched:
            print(f'FAIL: toolbar skip keyword: {matched}')
        else:
            print('PASS: toolbar but no skip keyword')

    # CSS visibility
    style = driver.execute_script("""
        const el = arguments[0];
        const s = getComputedStyle(el);
        return {
          display: s.display,
          visibility: s.visibility,
          opacity: parseFloat(s.opacity || '1'),
          pointerEvents: s.pointerEvents,
          ariaHidden: el.getAttribute('aria-hidden') || ''
        };
    """, el)
    print(f'CSS style: {style}')
    
    if style.get("display") == "none":
        print('FAIL: display=none')
    elif style.get("visibility") == "hidden":
        print('FAIL: visibility=hidden')
    elif style.get("pointerEvents") == "none":
        print('FAIL: pointerEvents=none')
    elif style.get("opacity", 1) is not None and style.get("opacity", 1) < 0.2:
        print('FAIL: opacity < 0.2')
    elif style.get("ariaHidden", "").lower() == "true":
        print('FAIL: aria-hidden=true')
    else:
        print('PASS: CSS visibility')

    # rect
    rect = el.rect
    print(f'rect: {rect}')
    if rect.get("width", 0) < 24 or rect.get("height", 0) < 24:
        print('FAIL: too small')
    else:
        print('PASS: size OK')

finally:
    driver.quit()
