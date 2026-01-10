#!/usr/bin/env python3
"""调试脚本：检查页面元素结构"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

options = Options()
options.add_argument('--headless')
driver = webdriver.Chrome(options=options)

try:
    for url in ['http://localhost:3000/#/login', 'http://localhost:3000/#/register']:
        driver.get(url)
        time.sleep(2)
        
        print(f"\n{'='*60}")
        print(f"URL: {url}")
        print(f"{'='*60}")
        
        # 查找 mat-raised-button
        raised = driver.find_elements(By.CSS_SELECTOR, '[mat-raised-button]')
        print(f"\n[mat-raised-button] 元素: {len(raised)}")
        
        for i, el in enumerate(raised):
            try:
                text = (el.text or "").strip().replace('\n', ' ')[:40]
                aria = el.get_attribute('aria-label') or ''
                disabled = el.get_attribute('disabled')
                is_displayed = el.is_displayed()
                is_enabled = el.is_enabled()
                elem_class = (el.get_attribute('class') or '')[:60]
                
                print(f"\n  [{i+1}] text='{text}'")
                print(f"      aria='{aria}'")
                print(f"      displayed={is_displayed}, enabled={is_enabled}")
                print(f"      disabled_attr={disabled}")
                print(f"      class={elem_class}")
                
                # 检查是否在 toolbar 内
                in_toolbar = driver.execute_script("""
                    const el = arguments[0];
                    let p = el.parentElement;
                    let depth = 0;
                    while (p && depth < 5) {
                        const cls = (p.className || '').toLowerCase();
                        if (cls.includes('mat-toolbar')) return true;
                        p = p.parentElement;
                        depth++;
                    }
                    return false;
                """, el)
                print(f"      in_toolbar={in_toolbar}")
                
                # 检查是否会被提交按钮关键词匹配
                submit_keywords = ["submit", "login", "log in", "sign in", "register", 
                                  "send", "save", "confirm", "checkout", "buy", "order"]
                matched = [kw for kw in submit_keywords if kw in text.lower() or kw in aria.lower()]
                print(f"      submit_keywords_matched={matched}")
                
            except Exception as e:
                print(f"  [{i+1}] Error: {e}")
            
finally:
    driver.quit()
