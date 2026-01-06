"""
Interaction-Chaos-Engine (ICE)
拦截(Intercept) -> 篡改(Mutate) -> 记录(Record)
交互类 Bug 注入框架：操作无响应、导航错误、非预期错误反馈。
输出目录与现有视觉数据保持一致：dataset_injected/images/interaction/, raw_metadata/int_*.json
"""

import os
import time
import json
import uuid
import random
from datetime import datetime
from typing import List, Dict, Any, Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image, ImageDraw

# 目录常量（与视觉数据保持兼容）
OUTPUT_DIR = "dataset_injected"
IMG_INTERACTION_DIR = os.path.join(OUTPUT_DIR, "images", "interaction")
META_DIR = os.path.join(OUTPUT_DIR, "raw_metadata")
VIEWPORT_SIZE = (1920, 1080)

TARGET_URLS = [
    "https://www.w3.org/",
    "https://www.apache.org/",
    "https://www.debian.org/",
    "https://docs.python.org/3/",
]


class InteractionInjector:
    """交互类缺陷注入引擎 (ICE)"""

    def __init__(self, headless: bool = True, max_wait: int = 15):
        self.headless = headless
        self.max_wait = max_wait
        self.driver = self._setup_driver()
        self._ensure_dirs()

    # ---------- 基础设施 ----------
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
        driver.set_page_load_timeout(30)
        return driver

    def _ensure_dirs(self):
        os.makedirs(IMG_INTERACTION_DIR, exist_ok=True)
        os.makedirs(META_DIR, exist_ok=True)

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass

    # ---------- 工具函数 ----------
    def _wait_page_ready(self):
        try:
            WebDriverWait(self.driver, self.max_wait).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            print("[!] 页面加载等待超时，继续执行")
        time.sleep(2)
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, 0);")
        except Exception:
            pass

    def _get_element_info(self, element) -> Dict[str, Any]:
        """提取元素语义信息，用于报告和模板填充"""
        info = {
            "tag": element.tag_name.lower(),
            "text": "",
            "id": "",
            "class": "",
            "aria_label": "",
            "bbox": element.rect,
        }
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
            return f'{info["tag"]}#{info["id"]}'
        if info.get("class"):
            return f'{info["tag"]}.{info["class"].split()[0]}'
        return info.get("tag", "element")

    def _visualize_action(self, img_path: str, x: int, y: int) -> str:
        """在截图上画红点/同心圆，模拟点击位置"""
        img = Image.open(img_path).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        r1, r2 = 10, 20
        draw.ellipse((x - r1, y - r1, x + r1, y + r1), fill=(255, 0, 0, 200))
        draw.ellipse((x - r2, y - r2, x + r2, y + r2), outline=(255, 0, 0, 160), width=3)
        out = Image.alpha_composite(img, overlay)
        output_path = img_path.replace(".png", "_action.png")
        out.save(output_path)
        return output_path

    def _expected_behavior(self, bug_type: str) -> str:
        mapping = {
            "Operation_No_Response": "Click should trigger navigation or state change.",
            "Navigation_Error": "Click should navigate to the correct destination.",
            "Unexpected_Task_Result": "Action should complete without system error banners.",
        }
        return mapping.get(bug_type, "Action should complete successfully.")

    # ---------- Mutator 策略 ----------
    def inject_operation_no_response(self, element) -> Tuple[str, str]:
        """操作无响应：移除事件监听并阻止默认行为"""
        self.driver.execute_script(
            """
            var el = arguments[0];
            var newEl = el.cloneNode(true);
            el.parentNode.replaceChild(newEl, el);
            newEl.style.pointerEvents = 'auto';
            newEl.onclick = function(e){ e.preventDefault(); e.stopPropagation(); return false; };
        """,
            element,
        )
        return "Operation_No_Response", "Click action triggers no navigation or state change."

    def inject_navigation_error(self, element) -> Tuple[str, str]:
        """导航错误：修改 href 指向错误地址"""
        original_href = element.get_attribute("href") or "(none)"
        fake_href = "#"
        self.driver.execute_script(
            f"""
            arguments[0].setAttribute('href', '{fake_href}');
            arguments[0].setAttribute('target', '_self');
        """,
            element,
        )
        return "Navigation_Error", f"Expected navigation to {original_href}, but stayed on page (or went to #)."

    def inject_unexpected_feedback(self, element) -> Tuple[str, str]:
        """非预期反馈：点击后弹出错误横幅"""
        self.driver.execute_script(
            """
            var el = arguments[0];
            el.onclick = function(e){
                e.preventDefault(); e.stopPropagation();
                var errDiv = document.createElement('div');
                errDiv.innerHTML = 'System Error: 500 Internal Server Error (ICE)';
                errDiv.style.cssText = 'position:fixed;top:0;left:0;width:100%;background:red;color:white;z-index:99999;font-size:22px;padding:16px;text-align:center;';
                document.body.appendChild(errDiv);
            };
        """,
            element,
        )
        return "Unexpected_Task_Result", "Action triggered a fake system error banner."

    # ---------- 主流程 ----------
    def get_candidates(self) -> List[Any]:
        sels = ["a", "button", "input[type='submit']", "input[type='button']"]
        elems = []
        for sel in sels:
            try:
                elems.extend(self.driver.find_elements(By.CSS_SELECTOR, sel))
            except Exception:
                continue
        candidates = []
        for el in elems:
            try:
                if not el.is_displayed():
                    continue
                rect = el.rect
                if rect.get("width", 0) < 20 or rect.get("height", 0) < 20:
                    continue
                candidates.append(el)
            except Exception:
                continue
        return candidates

    def run_on_url(self, url: str, samples_per_site: int = 3):
        print(f"[*] Loading: {url}")
        self.driver.get(url)
        self._wait_page_ready()

        candidates = self.get_candidates()
        if not candidates:
            print("[-] No valid interactive elements, skip")
            return

        for _ in range(samples_per_site):
            target = random.choice(candidates)
            self.execute_injection(target)
            time.sleep(0.5)

    def execute_injection(self, element, bug_choice: str | None = None):
        """执行一次完整交互注入"""
        uid = f"int_{uuid.uuid4().hex[:8]}"
        bug_type_key = bug_choice or random.choice(["no_response", "nav_error", "fake_error"])

        elem_info = self._get_element_info(element)
        bbox = elem_info.get("bbox", {"x": 0, "y": 0, "width": 0, "height": 0})
        center_x = int(bbox.get("x", 0) + bbox.get("width", 0) / 2)
        center_y = int(bbox.get("y", 0) + bbox.get("height", 0) / 2)

        # 截图 T0
        t0_path = os.path.join(IMG_INTERACTION_DIR, f"{uid}_step1_start.png")
        self.driver.save_screenshot(t0_path)
        # 生成动作视图（带红点）
        t0_action_path = self._visualize_action(t0_path, center_x, center_y)

        # 注入与动作
        if bug_type_key == "no_response":
            bug_type, desc = self.inject_operation_no_response(element)
            click_script = f"document.elementFromPoint({center_x}, {center_y}).click();"
            self.driver.execute_script(click_script)
        elif bug_type_key == "nav_error":
            bug_type, desc = self.inject_navigation_error(element)
            try:
                element.click()
            except Exception:
                self.driver.execute_script(f"document.elementFromPoint({center_x}, {center_y}).click();")
        else:
            bug_type, desc = self.inject_unexpected_feedback(element)
            try:
                element.click()
            except Exception:
                self.driver.execute_script(f"document.elementFromPoint({center_x}, {center_y}).click();")

        time.sleep(1.5)
        t1_path = os.path.join(IMG_INTERACTION_DIR, f"{uid}_step2_end.png")
        self.driver.save_screenshot(t1_path)

        # 记录元数据
        meta = {
            "id": uid,
            "bug_category": "interaction",
            "bug_type": bug_type,
            "description": desc,
            "expected_behavior": self._expected_behavior(bug_type),
            "url": self.driver.current_url,
            "element_semantic": elem_info,
            "action_trace": {
                "action": "click",
                "coordinates": [center_x, center_y],
                "target_readable": elem_info.get("readable_name"),
            },
            "images": {
                "start": os.path.relpath(t0_path, OUTPUT_DIR).replace("\\", "/"),
                "action": os.path.relpath(t0_action_path, OUTPUT_DIR).replace("\\", "/"),
                "end": os.path.relpath(t1_path, OUTPUT_DIR).replace("\\", "/"),
            },
            "timestamp": str(datetime.now()),
        }
        meta_path = os.path.join(META_DIR, f"{uid}.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"[+] Interaction bug injected: {uid} | {bug_type}")

    def run_batch(self, sites: List[str], samples_per_site: int = 3):
        for site in sites:
            try:
                self.run_on_url(site, samples_per_site)
            except Exception as e:
                print(f"[!] Failed on {site}: {e}")


if __name__ == "__main__":
    injector = InteractionInjector(headless=True)
    try:
        injector.run_batch(TARGET_URLS, samples_per_site=2)
    finally:
        injector.close()
