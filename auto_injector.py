import os
import json
import time
import random
import uuid
import math
from datetime import datetime
from PIL import Image, ImageChops  # 新增依赖
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# ================= 配置区域 =================

# [重要] 调试模式开关
# True  = 调试模式：生成的图片会有红色边框，且不会进行像素差异过滤（方便肉眼检查位置）。
# False = 生产模式：生成的图片干净无标记，且会自动丢弃肉眼看不出差异的废图（用于训练AI）。
DEBUG_MODE = True  

OUTPUT_DIR = "dataset_injected"
IMG_DIR = os.path.join(OUTPUT_DIR, "images")
LBL_DIR = os.path.join(OUTPUT_DIR, "labels")
META_DIR = os.path.join(OUTPUT_DIR, "metadata")

# 模拟的视口大小 (PC端)
VIEWPORT_SIZE = (1920, 1080)

# 目标网站列表 (替换为结构标准、易于注入的网站)
TARGET_URLS = [
    "https://www.w3.org/",                   # HTML标准结构
    "https://www.apache.org/",               # 传统文本密集型
    "https://www.debian.org/",               # 极简HTML，无复杂CSS防御
    "https://docs.python.org/3/",            # 文档结构
    "https://en.wikipedia.org/wiki/Software_testing", # Wiki结构
    "https://www.eclipse.org/"               # 传统门户
]
# ===========================================

class AutoInjector:
    def __init__(self):
        self._setup_driver()
        self._ensure_dirs()

    def _setup_driver(self):
        """初始化无头浏览器"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument(f"--window-size={VIEWPORT_SIZE[0]},{VIEWPORT_SIZE[1]}")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--ignore-certificate-errors")
        # 策略: eager (DOM加载完即开始，不等待所有图片)
        chrome_options.page_load_strategy = 'eager'
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.set_page_load_timeout(30)

    def _ensure_dirs(self):
        for d in [IMG_DIR, LBL_DIR, META_DIR]:
            os.makedirs(d, exist_ok=True)

    def wait_for_page_ready(self):
        """智能等待"""
        try:
            WebDriverWait(self.driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except:
            print("[!] 页面状态等待超时，尝试继续...")
        time.sleep(2) 

    def load_page(self, url):
        print(f"[*] 正在加载: {url}")
        try:
            self.driver.get(url)
        except Exception as e:
            print(f"[!] 加载超时或中断: {e}")
            self.driver.execute_script("window.stop();")
        
        self.wait_for_page_ready()

    def get_candidate_elements(self):
        """寻找可注入元素，增加幽灵元素过滤"""
        candidates = []
        try:
            selectors = [
                ("//button", By.XPATH), ("//a", By.XPATH), ("//input", By.XPATH),
                ("//img", By.XPATH), ("//h1|//h2|//h3", By.XPATH), ("//p", By.XPATH),
                ("//div[@class or @id]", By.XPATH)
            ]
            
            for selector, by in selectors:
                elements = self.driver.find_elements(by, selector)
                # 随机采样，避免只取头部元素
                sample_elements = random.sample(elements, min(len(elements), 30))
                
                for elem in sample_elements:
                    try:
                        if not elem.is_displayed(): continue
                        
                        rect = self.driver.execute_script("return arguments[0].getBoundingClientRect();", elem)
                        
                        # 1. 尺寸过滤
                        if rect['width'] < 20 or rect['height'] < 20: continue
                        if rect['width'] > 1200 or rect['height'] > 900: continue
                        
                        # 2. 坐标过滤 (排除负坐标)
                        if rect['x'] < 0 or rect['y'] < 0: continue

                        # 3. [新增] 幽灵元素过滤 (针对透明且无内容的 div/span)
                        tag = elem.tag_name.lower()
                        if tag in ['div', 'span', 'section']:
                            has_text = self.driver.execute_script("return arguments[0].innerText.trim().length > 0", elem)
                            if not has_text:
                                bg = elem.value_of_css_property('background-color')
                                bd = elem.value_of_css_property('border-width')
                                # 如果背景透明且无边框，视为幽灵元素，跳过
                                if bg == 'rgba(0, 0, 0, 0)' and (not bd or bd == '0px'):
                                    continue

                        candidates.append(elem)
                    except:
                        continue
            return candidates
        except Exception as e:
            print(f"[!] 元素查找异常: {e}")
            return []

    def scroll_to_element(self, element):
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.5)

    def inject_bug(self, element, bug_type):
        """执行故障注入"""
        bug_info = {}
        
        # 定义视觉辅助样式 (仅在 DEBUG_MODE 下生效)
        visual_aid = ""
        if DEBUG_MODE:
            visual_aid = "arguments[0].style.border = '3px solid red'; arguments[0].style.boxShadow = '0 0 10px red';"
        
        try:
            if not element.is_displayed(): return False, None
            self.scroll_to_element(element)
            
            # 获取初始坐标
            rect = self.driver.execute_script("return arguments[0].getBoundingClientRect();", element)
            current_bbox = {"x": rect['x'], "y": rect['y'], "width": rect['width'], "height": rect['height']}

            # 注入前视口检查
            if not self._is_in_viewport(current_bbox): return False, None

            script = ""
            if bug_type == "Layout_Overlap":
                offset_x = random.choice([-50, 50])
                offset_y = random.choice([40, -40])
                script = f"""
                arguments[0].style.transform = 'translate({offset_x}px, {offset_y}px)';
                arguments[0].style.position = 'relative';
                arguments[0].style.zIndex = '99999';
                {visual_aid}
                """
                self.driver.execute_script(script, element)
                current_bbox['x'] += offset_x
                current_bbox['y'] += offset_y

            elif bug_type == "Element_Missing":
                # 隐藏元素，如果是DEBUG模式，放一个红色占位符
                placeholder_script = ""
                if DEBUG_MODE:
                    placeholder_script = """
                    const p = document.createElement('div');
                    p.style.cssText = 'width:'+arguments[0].offsetWidth+'px;height:'+arguments[0].offsetHeight+'px;border:2px dashed red;background:rgba(255,0,0,0.1);';
                    arguments[0].parentNode.insertBefore(p, arguments[0]);
                    """
                script = f"""
                {placeholder_script}
                arguments[0].style.visibility = 'hidden';
                """
                self.driver.execute_script(script, element)

            elif bug_type == "Text_Overflow":
                long_text = "ERROR_OVERFLOW_" * 20
                bg_style = "arguments[0].style.backgroundColor = 'rgba(255,0,0,0.2)';" if DEBUG_MODE else ""
                script = f"""
                arguments[0].style.position = 'relative';
                arguments[0].style.zIndex = '9999';
                arguments[0].style.whiteSpace = 'nowrap';
                arguments[0].style.overflow = 'visible';
                arguments[0].innerText = '{long_text}';
                {bg_style}
                {visual_aid}
                """
                self.driver.execute_script(script, element)
                # 重新获取尺寸
                rect = self.driver.execute_script("return arguments[0].getBoundingClientRect();", element)
                current_bbox = {"x": rect['x'], "y": rect['y'], "width": rect['width'], "height": rect['height']}

            elif bug_type == "Broken_Image":
                # 仅针对 img 标签
                if element.tag_name.lower() != 'img': return False, None
                border_style = "1px solid red" if DEBUG_MODE else "1px solid #ccc"
                script = f"""
                let w = arguments[0].offsetWidth;
                let h = arguments[0].offsetHeight;
                arguments[0].src = 'http://invalid-url-404.jpg';
                arguments[0].alt = 'Broken Image';
                arguments[0].style.width = w + 'px';
                arguments[0].style.height = h + 'px';
                arguments[0].style.display = 'inline-block';
                arguments[0].style.border = '{border_style}';
                arguments[0].style.objectFit = 'contain';
                """
                self.driver.execute_script(script, element)

            bug_info = {"type": bug_type, "bbox": current_bbox, "script": script}
            return True, bug_info

        except Exception:
            return False, None

    def _calculate_image_diff(self, img_path1, img_path2):
        """计算图片差异 (RMS)"""
        try:
            img1 = Image.open(img_path1).convert('RGB')
            img2 = Image.open(img_path2).convert('RGB')
            if img1.size != img2.size: return 100.0
            diff = ImageChops.difference(img1, img2)
            h = diff.histogram()
            sq = (value * ((idx % 256) ** 2) for idx, value in enumerate(h))
            sum_of_squares = sum(sq)
            rms = math.sqrt(sum_of_squares / float(img1.size[0] * img1.size[1]))
            return rms
        except:
            return 0.0

    def _is_in_viewport(self, bbox):
        vp_w, vp_h = VIEWPORT_SIZE
        if bbox['width'] <= 0 or bbox['height'] <= 0: return False
        x1, y1 = max(bbox['x'], 0), max(bbox['y'], 0)
        x2, y2 = min(bbox['x'] + bbox['width'], vp_w), min(bbox['y'] + bbox['height'], vp_h)
        inter_area = max(0, x2 - x1) * max(0, y2 - y1)
        return (inter_area / (bbox['width'] * bbox['height'])) > 0.5

    def save_dataset_pair(self, url):
        pair_id = str(uuid.uuid4())[:8]
        max_retries = 3
        
        # 每次生成前先清理环境
        self.remove_popups_and_fixed_elements()

        for attempt in range(max_retries):
            try:
                candidates = self.get_candidate_elements()
                if not candidates: break
                
                target = random.choice(candidates)
                
                # --- Normal 截图 ---
                self.scroll_to_element(target)
                rect = self.driver.execute_script("return arguments[0].getBoundingClientRect();", target)
                normal_bbox = {"x": rect['x'], "y": rect['y'], "width": rect['width'], "height": rect['height']}
                
                if not self._is_in_viewport(normal_bbox): continue

                normal_path = os.path.join(IMG_DIR, f"{pair_id}_normal.png")
                self.driver.save_screenshot(normal_path)
                
                # --- Bug 注入 ---
                bug_type = random.choice(["Layout_Overlap", "Element_Missing", "Text_Overflow", "Broken_Image"])
                success, info = self.inject_bug(target, bug_type)
                
                if not success: 
                    self._reset_page()
                    continue

                # --- Buggy 截图 ---
                time.sleep(0.5)
                buggy_path = os.path.join(IMG_DIR, f"{pair_id}_buggy.png")
                self.driver.save_screenshot(buggy_path)
                
                # --- 校验逻辑 ---
                # 只有在关闭调试模式时，才进行像素校验
                valid_sample = True
                diff_score = 0.0
                
                if not DEBUG_MODE:
                    diff_score = self._calculate_image_diff(normal_path, buggy_path)
                    # 阈值设定：如果差异太小，说明注入无效
                    if diff_score < 2.0:
                        print(f"[-] {pair_id} 差异过小 (RMS={diff_score:.2f})，丢弃")
                        try:
                            os.remove(normal_path)
                            os.remove(buggy_path)
                        except: pass
                        valid_sample = False
                
                if valid_sample:
                    label_data = {
                        "id": pair_id, "url": url, "bug_type": info['type'],
                        "bbox": info['bbox'], "diff_score": diff_score,
                        "image_size": VIEWPORT_SIZE, "timestamp": str(datetime.now())
                    }
                    with open(os.path.join(META_DIR, f"{pair_id}.json"), "w") as f:
                        json.dump(label_data, f, indent=2)
                    print(f"[+] 成功: {pair_id} | {info['type']} | Diff: {diff_score:.2f}")
                    break # 成功退出循环
                else:
                    self._reset_page()

            except Exception as e:
                print(f"[!] 尝试 {attempt} 异常: {str(e)[:50]}")
                self._reset_page()

        # 无论成功与否，最后刷新页面保持环境
        self._reset_page()

    def _reset_page(self):
        try:
            self.driver.refresh()
            self.wait_for_page_ready()
            self.remove_popups_and_fixed_elements()
        except: pass

    def remove_popups_and_fixed_elements(self):
        """清理弹窗脚本"""
        script = """
        (function() {
            const keywords = ['cookie', 'consent', 'popup', 'modal', 'overlay'];
            document.querySelectorAll('div,section,header,dialog').forEach(el => {
                const s = window.getComputedStyle(el);
                const r = el.getBoundingClientRect();
                const id_cls = (el.id + " " + el.className).toLowerCase();
                
                if (s.position === 'fixed' || s.position === 'sticky') {
                    if (r.width > window.innerWidth * 0.8 && r.height < window.innerHeight * 0.6) el.remove();
                }
                if (parseInt(s.zIndex) > 100 && r.width > window.innerWidth * 0.9) el.remove();
                if (keywords.some(k => id_cls.includes(k)) && s.display !== 'none') el.remove();
            });
            document.body.style.overflow = 'auto';
        })();
        """
        try: self.driver.execute_script(script)
        except: pass

    def run(self):
        print(f"=== 开始运行 | DEBUG_MODE: {DEBUG_MODE} ===")
        for url in TARGET_URLS:
            try:
                self.load_page(url)
                for _ in range(3): # 每个网站生成数量
                    self.save_dataset_pair(url)
            except Exception as e:
                print(f"[!] 网站 {url} 失败: {e}")
        self.driver.quit()
        print("=== 完成 ===")

if __name__ == "__main__":
    injector = AutoInjector()
    injector.run()