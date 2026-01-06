import os
import json
import time
import random
import uuid
import math
from datetime import datetime
from PIL import Image, ImageChops, ImageDraw, ImageFont  # 新增 ImageDraw, ImageFont
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
IMG_DIR = os.path.join(OUTPUT_DIR, "images", "visual")  # 视觉类 Bug 图片
LBL_DIR = os.path.join(OUTPUT_DIR, "labels")
META_DIR = os.path.join(OUTPUT_DIR, "raw_metadata")  # 原始元数据

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
        self.lock_viewport = True  # 锁定视口滚动位置，保证成对截图一致

    def _normalize_bbox(self, bbox):
        """将像素坐标归一化到 [0,1] 便于跨分辨率训练"""
        try:
            w, h = VIEWPORT_SIZE
            return {
                "x": bbox["x"] / w,
                "y": bbox["y"] / h,
                "width": bbox["width"] / w,
                "height": bbox["height"] / h,
            }
        except:
            return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    
    def _extract_semantic_info(self, element):
        """提取元素的语义信息（关键创新：零成本标注）"""
        try:
            semantic = {
                "tag": element.tag_name.lower(),
                "text": "",
                "aria_label": "",
                "id": "",
                "class": "",
                "role": "",
                "placeholder": "",
                "type": "",
                "name": ""
            }
            
            # 提取文本内容（截断长文本）
            try:
                text = element.text.strip()
                if len(text) > 100:
                    text = text[:100] + "..."
                semantic["text"] = text
            except: pass
            
            # 提取属性
            for attr in ["aria-label", "id", "class", "role", "placeholder", "type", "name"]:
                try:
                    val = element.get_attribute(attr)
                    if val:
                        key = attr.replace("-", "_")
                        semantic[key] = str(val)[:100]  # 截断
                except: pass
            
            # 如果没有 text 但有 value（如 input）
            if not semantic["text"]:
                try:
                    value = element.get_attribute("value")
                    if value:
                        semantic["text"] = value[:100]
                except: pass
            
            # 生成人类可读的描述（用于模板填充）
            semantic["readable_name"] = self._generate_readable_name(semantic)
            
            return semantic
        except Exception as e:
            return {"tag": "unknown", "readable_name": "页面元素"}
    
    def _generate_readable_name(self, semantic):
        """从语义信息生成人类可读的元素名称"""
        # 优先级：text > aria-label > id > class > tag
        if semantic.get("text") and len(semantic["text"]) < 30:
            return f'"{semantic["text"]}"按钮' if semantic["tag"] == "button" else f'"{semantic["text"]}"'
        if semantic.get("aria_label"):
            return f'"{semantic["aria_label"]}"'
        if semantic.get("placeholder"):
            return f'输入框（{semantic["placeholder"]}）'
        if semantic.get("id"):
            return f'{semantic["tag"]}#{semantic["id"]}'
        if semantic.get("class"):
            classes = semantic["class"].split()[0]  # 只取第一个类名
            return f'{semantic["tag"]}.{classes}'
        
        # 回退到标签类型
        tag_names = {
            "button": "按钮",
            "a": "链接",
            "input": "输入框",
            "img": "图片",
            "h1": "标题",
            "h2": "二级标题",
            "h3": "三级标题",
            "p": "段落",
            "div": "容器",
            "span": "文本",
            "select": "下拉框",
            "textarea": "文本域"
        }
        return tag_names.get(semantic.get("tag"), semantic.get("tag", "元素"))
    
    def _get_expected_behavior(self, bug_type):
        """[改进 3] 为每种 Bug 类型定义预期行为（Ground Truth）"""
        behaviors = {
            "Layout_Overlap": "元素应位于正确的位置，不与其他内容重叠",
            "Element_Missing": "关键元素应当可见，用户应能正常交互",
            "Text_Overflow": "文本应完整显示在容器内，不应溢出或被截断",
            "Broken_Image": "图片应正常加载并显示",
            "Layout_Alignment": "元素应按设计规范对齐，保持视觉一致性",
            "Layout_Spacing": "元素间距应统一，符合设计系统规范",
            "Data_Format_Error": "数据应以正确的格式展示（日期、数字、货币等）",
            "Style_Color_Contrast": "文本与背景的对比度应≥4.5:1（WCAG AA标准）",
            "Style_Size_Inconsistent": "同类元素的尺寸应保持一致"
        }
        return behaviors.get(bug_type, "元素应正常工作")
    
    def _draw_action_marker(self, image_path, bbox, action_type="click", output_path=None):
        """[改进 3] 在截图上绘制动作标记（红点/箭头）用于交互类 Bug
        
        Args:
            image_path: 原始截图路径
            bbox: 元素坐标 {"x", "y", "width", "height"}
            action_type: "click" | "hover" | "type"
            output_path: 输出路径（默认覆盖原图）
        
        Returns:
            标记后的图片路径
        """
        try:
            img = Image.open(image_path)
            draw = ImageDraw.Draw(img)
            
            # 计算元素中心点
            center_x = int(bbox["x"] + bbox["width"] / 2)
            center_y = int(bbox["y"] + bbox["height"] / 2)
            
            if action_type == "click":
                # 绘制红色圆点（模拟鼠标点击）
                radius = 10
                draw.ellipse(
                    [center_x - radius, center_y - radius, 
                     center_x + radius, center_y + radius],
                    fill=(255, 0, 0),  # 红色填充
                    outline=(255, 255, 255),  # 白色边框
                    width=3
                )
                # 内部小圆（增强视觉效果）
                inner_radius = 3
                draw.ellipse(
                    [center_x - inner_radius, center_y - inner_radius,
                     center_x + inner_radius, center_y + inner_radius],
                    fill=(255, 255, 255)
                )
            
            elif action_type == "hover":
                # 绘制黄色光晕（模拟悬停）
                radius = 12
                draw.ellipse(
                    [center_x - radius, center_y - radius,
                     center_x + radius, center_y + radius],
                    fill=(255, 255, 0, 100),  # 半透明黄色
                    outline=(255, 200, 0),
                    width=2
                )
            
            elif action_type == "type":
                # 绘制蓝色光标（模拟输入）
                cursor_height = 20
                draw.rectangle(
                    [center_x - 1, center_y - cursor_height // 2,
                     center_x + 1, center_y + cursor_height // 2],
                    fill=(0, 0, 255)
                )
            
            # 保存
            if not output_path:
                output_path = image_path
            img.save(output_path)
            return output_path
            
        except Exception as e:
            print(f"[!] 绘制动作标记失败: {e}")
            return image_path

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
        """智能等待，确保页面完全渲染"""
        try:
            # 等待 DOM 完成
            WebDriverWait(self.driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except:
            print("[!] 页面状态等待超时，尝试继续...")
        
        # 额外等待，让 CSS/字体/图片渲染
        time.sleep(3)
        
        # 滚动到底部再回顶部，触发懒加载
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
        except:
            pass 

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
            noisy_keywords = ['carousel', 'slider', 'slick', 'swiper', 'marquee', 'ad', 'ads', 'advert', 'sponsor', 'banner', 'promo']
            
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

                        # 3. 过滤易引起重排或广告区域（轮播/广告位不稳定）
                        try:
                            id_cls = (elem.get_attribute('id') or '').lower() + ' ' + (elem.get_attribute('class') or '').lower()
                            if any(k in id_cls for k in noisy_keywords):
                                continue
                        except:
                            pass

                        # 4. [新增] 幽灵元素过滤 (针对透明且无内容的 div/span)
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

    def pause_animations(self):
        """禁用页面动画/过渡，减少重排导致的定位偏移"""
        script = """
        try {
            const all = Array.from(document.querySelectorAll('*'));
            all.forEach(el => {
                el.style.animation = 'none !important';
                el.style.transition = 'none !important';
            });
        } catch(e) {}
        """
        try:
            self.driver.execute_script(script)
        except:
            pass

    def scroll_to_element(self, element):
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.5)

    def get_scroll_y(self):
        try:
            return int(self.driver.execute_script("return Math.round(window.pageYOffset || window.scrollY || 0);"))
        except:
            return 0

    def set_scroll_y(self, y):
        try:
            self.driver.execute_script("window.scrollTo(0, arguments[0]);", y)
        except:
            pass

    def _add_debug_overlay(self, bbox):
        """在页面上方添加一个红色矩形覆盖层，仅用于 DEBUG 截图。"""
        if not DEBUG_MODE:
            return
        try:
            self.driver.execute_script(
                """
                (function(b){
                    let o = document.getElementById('__debug_overlay__');
                    if(!o){
                        o = document.createElement('div');
                        o.id='__debug_overlay__';
                        o.style.position='absolute';
                        o.style.pointerEvents='none';
                        o.style.zIndex='2147483647';
                        document.body.appendChild(o);
                    }
                    o.style.border='4px solid red';
                    o.style.boxShadow='0 0 15px red';
                    o.style.left = (b.x + window.scrollX) + 'px';
                    o.style.top = (b.y + window.scrollY) + 'px';
                    o.style.width = b.width + 'px';
                    o.style.height = b.height + 'px';
                    o.style.display='block';
                })({x: arguments[0].x, y: arguments[0].y, width: arguments[0].width, height: arguments[0].height});
                """,
                bbox,
            )
        except:
            pass

    def _remove_debug_overlay(self):
        if not DEBUG_MODE:
            return
        try:
            self.driver.execute_script(
                """
                const o = document.getElementById('__debug_overlay__');
                if(o) o.style.display='none';
                """
            )
        except:
            pass

    def inject_bug(self, element, bug_type):
        """执行故障注入"""
        bug_info = {}
        
        # 调试时不在元素本身添加任何红框，统一由截图前的 overlay 显示
        visual_aid = ""
        
        try:
            if not element.is_displayed(): return False, None
            self.scroll_to_element(element)
            
            # 获取初始坐标
            rect = self.driver.execute_script("return arguments[0].getBoundingClientRect();", element)
            current_bbox = {"x": rect['x'], "y": rect['y'], "width": rect['width'], "height": rect['height']}

            # 过滤掉过小的元素（注入效果不明显）
            min_width, min_height = 30, 15
            if current_bbox['width'] < min_width or current_bbox['height'] < min_height:
                return False, None

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
                    # 使用微弱背景占位，避免产生第二个红框
                    placeholder_script = """
                    const p = document.createElement('div');
                    p.style.cssText = 'width:'+arguments[0].offsetWidth+'px;height:'+arguments[0].offsetHeight+"px;background:rgba(255,0,0,0.06);border:none;outline:none;";
                    arguments[0].parentNode.insertBefore(p, arguments[0]);
                    """
                script = f"""
                {placeholder_script}
                arguments[0].style.visibility = 'hidden';
                """
                self.driver.execute_script(script, element)

            elif bug_type == "Text_Overflow":
                long_text = "ERROR_OVERFLOW_" * 30
                bg_style = "arguments[0].style.backgroundColor = 'rgba(255,0,0,0.15)';" if DEBUG_MODE else ""
                script = f"""
                (function(el) {{
                    const tag = (el.tagName || '').toLowerCase();
                    const isInput = tag === 'input' || tag === 'textarea';
                    if (isInput) {{
                        el.value = '{long_text}';
                        el.removeAttribute('maxlength');
                        el.style.whiteSpace = 'nowrap';
                        el.style.overflow = 'visible';
                        el.style.minWidth = (el.offsetWidth * 2) + 'px';
                        el.style.width = (el.offsetWidth * 2.5) + 'px';
                    }} else {{
                        el.style.whiteSpace = 'nowrap';
                        el.style.overflow = 'visible';
                        el.textContent = '{long_text}';
                    }}
                    el.style.position = 'relative';
                    el.style.zIndex = '9999';
                    {bg_style}
                    {visual_aid}
                }})(arguments[0]);
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

            elif bug_type == "Layout_Alignment":
                # 通过不当的偏移或内边距制造对齐问题
                # 跳过表单元素（偏移不够明显）
                tag = element.tag_name.lower()
                if tag in ['input', 'textarea', 'select']:
                    return False, None
                shift_px = random.randint(24, 48)
                use_padding = random.random() < 0.4
                prop = random.choice(["paddingLeft", "paddingTop"]) if use_padding else random.choice(["marginLeft", "marginRight", "marginTop"])
                script = f"""
                const el = arguments[0];
                el.style.position = 'relative';
                el.style.{prop} = '{shift_px}px';
                el.style.transition = 'none';
                {visual_aid}
                """
                self.driver.execute_script(script, element)
                # 对齐偏移不会显著改变自身 bbox，这里保留原 bbox

            elif bug_type == "Layout_Spacing":
                # 在容器内随机拉大/缩小部分子元素的间距
                # 跳过表单元素（无子元素或不适合此类缺陷）
                tag = element.tag_name.lower()
                if tag in ['input', 'textarea', 'select', 'button', 'img']:
                    return False, None
                child_count = self.driver.execute_script("return arguments[0].children ? arguments[0].children.length : 0;", element)
                if not child_count or child_count < 2:
                    return False, None
                script = f"""
                (function(el) {{
                    const kids = Array.from(el.children || []);
                    if (kids.length < 2) return;
                    const pickCount = Math.max(1, Math.floor(kids.length * 0.5));
                    for (let i = 0; i < pickCount; i++) {{
                        const kid = kids[Math.floor(Math.random() * kids.length)];
                        const delta = 20 + Math.floor(Math.random() * 25);
                        const prop = Math.random() > 0.5 ? 'marginTop' : 'marginBottom';
                        kid.style[prop] = delta + 'px';
                        kid.style.transition = 'none';
                    }}
                    {visual_aid}
                }})(arguments[0]);
                """
                self.driver.execute_script(script, element)

            elif bug_type == "Data_Format_Error":
                # 将 number 输入框填入非数字字符
                target_elem = element
                if element.tag_name.lower() != 'input' or (element.get_attribute('type') or '').lower() != 'number':
                    candidates = [el for el in self.driver.find_elements(By.CSS_SELECTOR, "input[type='number']") if el.is_displayed()]
                    if not candidates:
                        return False, None
                    target_elem = random.choice(candidates)
                    self.scroll_to_element(target_elem)

                invalid_value = random.choice(["abcXYZ", "NaN??", "###", "１２３abc", "error"])
                script = f"""
                const el = arguments[0];
                el.value = '{invalid_value}';
                el.setAttribute('data-injected','true');
                {visual_aid}
                """
                self.driver.execute_script(script, target_elem)
                rect = self.driver.execute_script("return arguments[0].getBoundingClientRect();", target_elem)
                current_bbox = {"x": rect['x'], "y": rect['y'], "width": rect['width'], "height": rect['height']}

            elif bug_type == "Style_Color_Contrast":
                # 故意降低文本与背景的对比度：使用更激进的方式让文本难以阅读
                script = fr"""
                (function(el) {{
                    el.offsetHeight;
                    const cs = window.getComputedStyle(el);
                    function parseColor(c) {{
                        const m = c.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
                        if (!m) return null;
                        return [parseInt(m[1]), parseInt(m[2]), parseInt(m[3])];
                    }}
                    const bg = parseColor(cs.backgroundColor) || [240, 240, 240];
                    // 策略: 直接使用背景色作为文本色（极端情况，文本不可见）
                    const textColor = `rgb(${{bg[0]}}, ${{bg[1]}}, ${{bg[2]}})`;
                    el.style.cssText += '; color: ' + textColor + ' !important; text-shadow: none !important; opacity: 0.6 !important;';
                    el.offsetHeight;
                    {visual_aid}
                }})(arguments[0]);
                """
                self.driver.execute_script(script, element)

            elif bug_type == "Style_Size_Inconsistent":
                # 让元素尺寸与同级元素不一致
                scale = round(random.uniform(0.75, 1.3), 2)
                width_factor = round(random.uniform(0.8, 1.25), 2)
                script = f"""
                const el = arguments[0];
                const rectNow = el.getBoundingClientRect();
                el.style.display = 'inline-block';
                el.style.transformOrigin = 'center center';
                el.style.transform = 'scale({scale})';
                el.style.width = (rectNow.width * {width_factor}) + 'px';
                el.style.boxSizing = 'border-box';
                {visual_aid}
                """
                self.driver.execute_script(script, element)
                rect = self.driver.execute_script("return arguments[0].getBoundingClientRect();", element)
                current_bbox = {"x": rect['x'], "y": rect['y'], "width": rect['width'], "height": rect['height']}

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

    def save_dataset_pair(self, url, bug_category="visual"):
        """生成一对 normal + buggy 的训练样本
        
        Args:
            url: 目标网站
            bug_category: 'visual' 或 'interaction'
        """
        # [改进 2] 文件命名：vis_ 或 int_ 前缀
        prefix = "vis" if bug_category == "visual" else "int"
        pair_id = f"{prefix}_{str(uuid.uuid4().hex[:8])}"
        max_retries = 3
        
        # 每次生成前先清理环境
        self.remove_popups_and_fixed_elements()
        # 关闭动画/过渡，避免注入后大幅重排
        self.pause_animations()

        for attempt in range(max_retries):
            try:
                candidates = self.get_candidate_elements()
                if not candidates: break
                
                target = random.choice(candidates)
                
                # [改进 1] 提取语义信息（零成本标注的核心）
                semantic_info = self._extract_semantic_info(target)
                
                # --- Normal 截图 ---
                self.scroll_to_element(target)
                rect = self.driver.execute_script("return arguments[0].getBoundingClientRect();", target)
                normal_bbox = {"x": rect['x'], "y": rect['y'], "width": rect['width'], "height": rect['height']}
                
                if not self._is_in_viewport(normal_bbox): continue
                # 记录滚动位置用于锁定
                scroll_y = self.get_scroll_y()

                # [视觉类 Bug] 保存 normal 截图
                normal_path = os.path.join(IMG_DIR, f"{pair_id}_normal.png")
                self.driver.save_screenshot(normal_path)
                
                # --- Bug 注入 ---
                bug_type = random.choice([
                    "Layout_Overlap", "Element_Missing", "Text_Overflow", "Broken_Image",
                    "Layout_Alignment", "Layout_Spacing", "Data_Format_Error",
                    "Style_Color_Contrast", "Style_Size_Inconsistent"
                ])
                success, info = self.inject_bug(target, bug_type)
                
                if not success: 
                    self._reset_page()
                    continue

                # 等待注入渲染 + 强制浏览器重排
                time.sleep(0.8)
                self.driver.execute_script("window.dispatchEvent(new Event('resize')); document.body.offsetHeight;")
                time.sleep(0.3)
                
                # --- Buggy 截图 ---
                # 锁定到注入前的滚动位置，确保两张图视口一致
                if self.lock_viewport:
                    self.set_scroll_y(scroll_y)
                    time.sleep(0.2)
                
                # 在锁定滚动后再添加临时调试覆盖层（尝试使用注入后的 bbox，更贴合元素实际位置）
                overlay_bbox = normal_bbox
                try:
                    rect_after = self.driver.execute_script("return arguments[0].getBoundingClientRect();", target)
                    if rect_after and rect_after.get('width', 0) > 0 and rect_after.get('height', 0) > 0:
                        overlay_bbox = {"x": rect_after['x'], "y": rect_after['y'], "width": rect_after['width'], "height": rect_after['height']}
                except:
                    pass
                try:
                    self._add_debug_overlay(overlay_bbox)
                except:
                    pass
                
                # [视觉类 Bug] 保存 buggy 截图
                buggy_path = os.path.join(IMG_DIR, f"{pair_id}_buggy.png")
                self.driver.save_screenshot(buggy_path)
                # [改进 2] 生成带动作标记的截图（红点），让 VLM 明确交互位置
                try:
                    self._draw_action_marker(buggy_path, overlay_bbox, action_type="click", output_path=buggy_path)
                except Exception as e:
                    print(f"[!] 标记动作失败: {e}")
                # 截图后立即移除覆盖层
                try:
                    self._remove_debug_overlay()
                except:
                    pass
                
                # --- 校验逻辑 ---
                # 即使在 DEBUG_MODE 下也计算 diff，以监控注入是否生效
                valid_sample = True
                diff_score = 0.0

                diff_score = self._calculate_image_diff(normal_path, buggy_path)
                # 在 DEBUG_MODE 下总是保存（用于肉眼检查），否则按 diff 阈值过滤
                if not DEBUG_MODE:
                    # 阈值设定：如果差异太小，说明注入无效
                    if diff_score < 2.0:
                        print(f"[-] {pair_id} 差异过小 (RMS={diff_score:.2f})，丢弃")
                        try:
                            os.remove(normal_path)
                            os.remove(buggy_path)
                        except: pass
                        valid_sample = False
                
                if valid_sample:
                    bbox_after = info['bbox']
                    label_data = {
                        "id": pair_id,
                        "url": url,
                        "bug_type": info['type'],
                        "bug_category": bug_category,
                        
                        # [改进 1] 语义信息（零成本标注的核心）
                        "element_semantic": semantic_info,
                        
                        # 坐标信息
                        "bbox_before": normal_bbox,
                        "bbox_after": bbox_after,
                        "bbox_before_norm": self._normalize_bbox(normal_bbox),
                        "bbox_after_norm": self._normalize_bbox(bbox_after),
                        
                        # 预期行为（Ground Truth）
                        "expected_behavior": self._get_expected_behavior(info['type']),
                        
                        # 验证指标
                        "diff_score": diff_score,
                        "image_size": VIEWPORT_SIZE,
                        "timestamp": str(datetime.now()),
                    }
                    if self.lock_viewport:
                        label_data["scroll_y"] = scroll_y
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