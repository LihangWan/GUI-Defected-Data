# 自动缺陷注入脚本说明 (auto_injector.py)

以下为各缺陷类型的实现细节、可见效果、关键约束与调试行为。脚本运行环境默认 `DEBUG_MODE = True`，会在截图时叠加红色调试框（由页面 overlay 绘制，不修改元素本身）。

## 通用机制
- 视口锁定：截图前记录 `scroll_y`，注入后恢复原滚动以保证 normal/buggy 对齐。
- 元素选择：过滤尺寸过小/过大、负坐标、幽灵元素（透明无内容），并跳过不稳定区域（类名/ID 含 carousel/slider/slick/swiper/ad/promo 等）。
- 动画冻结：每次生成前调用 `pause_animations()` 关闭全局 animation/transition，降低重排导致的偏移。
- 调试红框：截图前读取注入后 bbox（失败则用注入前），用 overlay 画红框；截图后移除。
- 差异校验：计算 normal vs buggy 的 RMS 差异，在 DEBUG_MODE 下仍保留全部样本，仅用于监控。

## 缺陷类型细节与改进分析（基于视觉识别）

### 1. Layout_Overlap (布局重叠)
**当前实现：**
- 做法：给目标元素 `transform: translate(...)`，偏移 ±50px (X) 与 ±40px (Y)，并 `position: relative; z-index: 99999`。
- 可见效果：元素与周围内容重叠、位置错位。
- 约束：更新 bbox 为偏移后的坐标。

**视觉特征随机性：** ⚠️ 偏低 - 仅4个固定偏移组合
**训练数据质量：** ⭐⭐⭐ 中等 - 效果明显但视觉模式单一

**视觉模型视角的问题：**
- ❌ 问题1：固定偏移量导致模型只学会识别"±50/±40像素的重叠"，泛化能力差
- ❌ 问题2：大小元素用相同偏移，视觉上"重叠程度"差异巨大（小元素完全移位 vs 大元素轻微错位）
- ❌ 问题3：只有水平或垂直偏移，缺少斜向重叠（视觉上是不同的模式）
- ❌ 问题4：z-index总是99999，元素永远在最上层，缺少"被遮挡"的重叠场景

**改进方案（视觉多样性）：**
```python
# 方案1：基于元素尺寸的比例偏移（视觉上更合理）
offset_ratio_x = random.uniform(0.2, 0.9)  # 偏移20%-90%的元素宽度
offset_ratio_y = random.uniform(0.2, 0.9)  
offset_x = int(current_bbox['width'] * offset_ratio_x) * random.choice([-1, 1])
offset_y = int(current_bbox['height'] * offset_ratio_y) * random.choice([-1, 1])

# 方案2：增加斜向重叠（50%概率同时X/Y偏移）
if random.random() > 0.5:
    # 同时X和Y偏移，视觉上是对角线移动
    offset_x = ...
    offset_y = ...
else:
    # 仅X或Y单向偏移
    offset_x = ... if random.random() > 0.5 else 0
    offset_y = ... if offset_x == 0 else 0

# 方案3：随机z-index（制造"被遮挡"场景）
z_index = random.choice([99999, -1, 0, 10])  # 负值或低值会被其他元素遮挡

# 方案4：增加小幅度重叠（10-30px）用于难样本
small_overlap = random.randint(10, 30) * random.choice([-1, 1])
```

**视觉效果增强：** 生成轻微重叠、严重重叠、斜向重叠、被遮挡等多种视觉模式

---

### 2. Element_Missing (元素消失)
**当前实现：**
- 做法：`visibility: hidden` 隐藏目标元素。DEBUG 模式下在原位插入浅红色占位 `<div>`。
- 可见效果：元素消失；调试时淡红块标示原位置。
- 约束：保留原 bbox（隐藏不变形）。

**视觉特征随机性：** ✅ 良好
**训练数据质量：** ⭐⭐⭐⭐ 优秀 - 视觉特征清晰

**视觉模型视角的问题：**
- ⚠️ 问题1：`visibility: hidden` 只有一种视觉表现，但真实场景中"消失"有多种视觉形态
- ✅ 实际上不同消失方式视觉效果不同：
  - `visibility: hidden` → 元素消失但留下**空白区域**（周围元素位置不变）
  - `display: none` → 元素消失且**周围元素会填补空白**（布局重排）
  - `opacity: 0` → 元素**透明**，可能看到被遮挡的背景

**改进方案（视觉多样性）：**
```python
# 三种消失方式产生不同视觉特征
disappear_method = random.choice([
    'visibility',  # 留空白（40%）
    'display',     # 布局重排（30%）  
    'opacity'      # 透明（30%）
])

if disappear_method == 'visibility':
    script = "arguments[0].style.visibility = 'hidden';"
    # 视觉特征：原位置有明显空白
elif disappear_method == 'display':
    script = "arguments[0].style.display = 'none';"
    # 视觉特征：元素完全消失，周围元素上移/左移填补
else:  # opacity
    script = "arguments[0].style.opacity = '0';"
    # 视觉特征：元素透明，可能露出背景纹理

# 增加"部分消失"（视觉上更难识别）
if random.random() > 0.8:  # 20%概率
    # 只隐藏文本内容，保留边框/背景
    script = """
    arguments[0].textContent = '';
    arguments[0].style.color = 'transparent';
    """
    # 视觉特征：空心的元素框架
```

**视觉效果增强：** 空白占位 vs 布局重排 vs 透明 vs 空心框架，模型需学会区分不同"消失"模式

---

### 3. Text_Overflow (文本溢出)
**当前实现：**
- 做法：写入固定字符串 "ERROR_OVERFLOW_" * 30；设置 `white-space: nowrap; overflow: visible;`。
- 可见效果：文字横向溢出。
- 约束：重取 bbox 记录放大后的尺寸。

**视觉特征随机性：** ⚠️ 偏低 - 固定字符串、固定方向
**训练数据质量：** ⭐⭐⭐ 中等 - 视觉模式单一

**视觉模型视角的问题：**
- ❌ 问题1：固定字符串"ERROR_OVERFLOW_"导致模型过拟合这个特定文本模式
- ❌ 问题2：仅横向溢出，缺少纵向溢出的视觉特征
- ❌ 问题3：溢出长度固定（30倍），视觉上总是"超长溢出"，缺少轻微溢出的难样本
- ❌ 问题4：所有溢出文本密度相同（字母紧密），缺少空格、符号、不同字符宽度的视觉差异

**改进方案（视觉多样性）：**
```python
# 方案1：随机生成不同视觉密度的文本
text_types = [
    'A' * 200,  # 窄字符，视觉上紧密
    'W' * 100,  # 宽字符，视觉上松散
    'https://example.com/very/long/url/path/to/resource/file.html?param=value&' * 5,  # URL（有斜杠分隔）
    '中文文本' * 50,  # 中文（视觉密度不同）
    '123.456.789.012.345' * 10,  # 数字+点（金融数据）
    'Word ' * 100,  # 带空格（可能换行）
    '___' * 100,  # 下划线（视觉上连成线）
]
long_text = random.choice(text_types)

# 方案2：随机溢出倍数（轻微溢出更难识别）
original_width = current_bbox['width']
overflow_multiplier = random.uniform(1.5, 5.0)  # 1.5x到5x
target_width = int(original_width * overflow_multiplier)

# 方案3：增加垂直溢出（视觉上完全不同）
if random.random() > 0.6:  # 40%概率垂直溢出
    long_text = '\n'.join(['行溢出文本'] * 50)
    script += """
    el.style.maxHeight = '50px';
    el.style.overflow = 'visible';
    el.style.whiteSpace = 'pre-wrap';
    """
    # 视觉特征：文本向下溢出，遮挡下方内容
else:  # 60%概率横向溢出
    script += """
    el.style.whiteSpace = 'nowrap';
    el.style.overflow = 'visible';
    """
    # 视觉特征：文本向右溢出

# 方案4：增加"截断错误"（视觉上是省略号但位置错误）
if random.random() > 0.85:  # 15%概率
    script += """
    el.style.textOverflow = 'ellipsis';
    el.style.overflow = 'hidden';
    el.style.width = '50px';  // 强制截断
    """
    # 视觉特征：文本中间或开头出现...
```

**视觉效果增强：** 不同文本密度、横向/纵向溢出、轻微/严重溢出、截断省略号等多种视觉模式

---

### 4. Broken_Image (图片损坏)
**当前实现：**
- 做法：替换 `src` 为无效链接；保留原宽高；设置边框。
- 可见效果：图片断裂占位或错误图标。
- 约束：bbox 不变。

**视觉特征随机性：** ⭐⭐ 中等 - 依赖浏览器默认断图样式
**训练数据质量：** ⭐⭐⭐ 良好 - 但视觉特征单一

**视觉模型视角的问题：**
- ❌ 问题1：依赖浏览器默认断图图标（Chrome是小方块，Firefox不同），视觉特征不可控
- ❌ 问题2：所有断图尺寸保持原样，缺少变形、拉伸的视觉错误
- ❌ 问题3：仅处理`<img>`标签，忽略了CSS背景图（视觉上也是图片）

**改进方案（视觉多样性）：**
```python
# 方案1：制造不同视觉表现的断图
broken_styles = [
    # 样式1：空白+边框（最常见）
    """
    el.src = 'data:image/gif;base64,invalid';
    el.alt = '';
    el.style.border = '1px solid #ccc';
    el.style.background = '#f5f5f5';
    """,
    
    # 样式2：显示alt文本（视觉上是文字）
    """
    el.src = 'http://invalid.jpg';
    el.alt = 'Image failed to load';
    el.style.fontSize = '12px';
    el.style.border = '1px dashed red';
    """,
    
    # 样式3：完全空白（无边框，更隐蔽）
    """
    el.src = '';
    el.alt = '';
    el.style.background = 'transparent';
    """,
    
    # 样式4：错误占位图案（对角线叉叉）
    """
    el.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"><line x1="0" y1="0" x2="100" y2="100" stroke="red"/></svg>';
    el.style.border = '2px solid red';
    """
]
script = random.choice(broken_styles)

# 方案2：增加尺寸变形（视觉上是拉伸/压缩）
if random.random() > 0.7:  # 30%概率变形
    deform_type = random.choice(['stretch_h', 'stretch_v', 'shrink'])
    if deform_type == 'stretch_h':
        script += f"el.style.width = '{int(original_width * 1.5)}px';"  # 横向拉伸
    elif deform_type == 'stretch_v':
        script += f"el.style.height = '{int(original_height * 1.8)}px';"  # 纵向拉伸
    else:
        script += "el.style.width = '20px'; el.style.height = '20px';"  # 缩成小方块

# 方案3：处理CSS背景图（扩展适用场景）
# 检测元素是否有background-image
has_bg_image = driver.execute_script("""
    const bg = window.getComputedStyle(arguments[0]).backgroundImage;
    return bg && bg !== 'none';
""", element)
if has_bg_image:
    script = """
    arguments[0].style.backgroundImage = 'url(http://invalid-bg.jpg)';
    arguments[0].style.backgroundSize = 'cover';
    arguments[0].style.border = '1px solid #f00';
    """
    # 视觉特征：背景消失，可能露出底色
```

**视觉效果增强：** 空白框、文字提示、完全空白、叉叉图案、拉伸变形、背景图损坏等多种视觉表现

---

### 5. Layout_Alignment (布局对齐)
**当前实现：**
- 做法：随机24-48px的margin/padding偏移。
- 可见效果：元素左右/上下错位。
- 约束：bbox维持原值。

**视觉特征随机性：** ⭐⭐ 中等
**训练数据质量：** ⭐⭐⭐ 中等 - 需要对比上下文

**视觉模型视角的问题：**
- ❌ 问题1：固定24-48px对不同尺寸屏幕/元素，视觉上的"错位程度"差异巨大
- ❌ 问题2：单个元素错位，缺少参照物，模型难以判断是否"不对齐"（需要对比同级元素）
- ❌ 问题3：仅处理margin/padding，忽略了文本对齐（text-align）的视觉错误

**改进方案（视觉可识别性）：**
```python
# ⚠️ 关键：对齐问题必须有视觉参照！单个元素无法判断是否"对齐错误"

# 方案1：找到同级元素，制造明显对比
siblings = driver.execute_script("""
    const parent = arguments[0].parentElement;
    return Array.from(parent.children).filter(el => 
        el !== arguments[0] && 
        el.offsetHeight > 20 && 
        window.getComputedStyle(el).display !== 'none'
    );
""", element)

if len(siblings) >= 2:
    # 只偏移目标元素，让同级元素保持对齐作为参照
    parent_width = driver.execute_script("return arguments[0].parentElement.offsetWidth;", element)
    shift_ratio = random.uniform(0.05, 0.15)  # 偏移父容器宽度的5%-15%
    shift_px = int(parent_width * shift_ratio)
    
    # 视觉特征：一排按钮中某一个向右/左偏移
    
# 方案2：文本对齐错误（视觉上非常明显）
if element.tag_name.lower() in ['p', 'h1', 'h2', 'h3', 'div']:
    current_align = element.value_of_css_property('text-align')
    wrong_aligns = [a for a in ['left', 'right', 'center'] if a != current_align]
    script = f"arguments[0].style.textAlign = '{random.choice(wrong_aligns)}';"
    # 视觉特征：段落突然左对齐/右对齐/居中（与周围不一致）

# 方案3：增加"缩进错误"（列表项、段落）
if element.tag_name.lower() in ['li', 'p']:
    indent_px = random.randint(30, 80)
    script = f"arguments[0].style.textIndent = '{indent_px}px';"
    # 视觉特征：首行缩进过大或错位
```

**视觉效果增强：** 必须包含参照元素（同级对比），增加文本对齐、缩进错误等明确的视觉特征

---

### 6. Layout_Spacing (布局间距)
**当前实现：**
- 做法：随机拉大50%子元素的marginTop/Bottom，增量20-45px。
- 可见效果：列表纵向间距不均。
- 约束：容器bbox微调。

**视觉特征随机性：** ⭐⭐⭐ 良好
**训练数据质量：** ⭐⭐⭐⭐ 优秀 - 视觉对比明显

**视觉模型视角的问题：**
- ⚠️ 问题1：仅垂直间距，缺少水平间距错误（如卡片横向排列）
- ⚠️ 问题2：仅"增大"间距，缺少"过小/重叠"的视觉错误
- ✅ 当前实现已经很好：通过修改部分子元素制造对比，视觉特征明确

**改进方案（视觉完整性）：**
```python
# 方案1：增加水平间距错误（针对横向布局）
layout_type = driver.execute_script("""
    const cs = window.getComputedStyle(arguments[0]);
    return cs.display === 'flex' && cs.flexDirection === 'row' ? 'horizontal' : 'vertical';
""", element)

if layout_type == 'horizontal':
    # 修改横向间距
    prop = random.choice(['marginLeft', 'marginRight'])
    # 视觉特征：横向卡片间距不一致
else:
    # 修改纵向间距（原有逻辑）
    prop = random.choice(['marginTop', 'marginBottom'])

# 方案2：增加"间距过小/负值"（视觉上是重叠）
spacing_error_type = random.choice(['too_large', 'too_small', 'negative'])
if spacing_error_type == 'too_large':
    delta = random.randint(30, 60)  # 过大
elif spacing_error_type == 'too_small':
    delta = random.randint(0, 3)    # 几乎无间距
else:
    delta = random.randint(-20, -5) # 负值导致重叠
# 视觉特征：元素挤在一起 vs 过度分散

# 方案3：制造"不规律间距"（视觉上是节奏感错误）
for i, kid in enumerate(kids):
    if i % 2 == 0:
        kid.style[prop] = f'{large_spacing}px'  # 偶数大间距
    else:
        kid.style[prop] = f'{small_spacing}px'  # 奇数小间距
# 视觉特征：1大1小1大1小的节奏
```

**视觉效果增强：** 垂直+水平、过大+过小+负值、规律性破坏等多种视觉模式

---

### 7. Data_Format_Error (数据格式错误)
**当前实现：**
- 做法：仅针对`input[type=number]`，填入"abcXYZ"等非数字。
- 可见效果：数字框显示非法字符。
- 约束：场景极度受限。

**视觉特征随机性：** ⭐⭐ 中等
**训练数据质量：** ⭐⭐ 偏低 - 适用场景太少

**视觉模型视角的问题：**
- ❌ 问题1：网页上number输入框很少，数据量严重不足
- ❌ 问题2：从视觉上看，模型需要识别的是"输入框内容与预期格式不符"，而不仅仅是number类型
- ✅ 应该扩展到所有有格式要求的输入框（视觉上都是"内容异常"）

**改进方案（扩展视觉场景）：**
```python
# 扩展到多种输入类型（视觉上都是"输入内容错误"）
input_types_and_errors = {
    'email': [
        'notanemail',           # 缺少@，视觉上明显错误
        'user@@domain.com',     # 双@
        'user @domain.com',     # 空格
        '用户名@域名.com',       # 中文（某些场景不允许）
    ],
    'tel': [
        'abcd-efgh',            # 字母
        '123',                  # 位数不够（视觉上短）
        '+++1234567890',        # 过多符号
    ],
    'url': [
        'not a url',            # 无协议
        'ht!tp://invalid',      # 错误协议
        'www .example. com',    # 空格
    ],
    'date': [
        '2023-13-45',           # 非法月日（视觉上数字看似正常）
        'not-a-date',           # 完全错误
        '99/99/9999',           # 错误分隔符
    ],
    'number': [
        'abc123',               # 字母+数字
        '1.2.3.4',              # 多个小数点
        '999999999999999999',   # 超长数字（视觉上溢出）
    ],
    'text': [  # 即使是text也可能有格式要求
        # 检测placeholder/label来推断预期格式
        # 如果placeholder包含"邮编"，填入"abcde"
        # 如果label包含"金额"，填入"$$$"
    ]
}

# 查找页面中所有有格式要求的输入框
format_inputs = driver.find_elements(By.CSS_SELECTOR, 
    "input[type='email'], input[type='tel'], input[type='url'], input[type='date'], input[type='number']")

if format_inputs:
    target = random.choice(format_inputs)
    input_type = target.get_attribute('type')
    invalid_value = random.choice(input_types_and_errors.get(input_type, ['ERROR']))
    # 视觉特征：输入框中的内容明显不符合格式（如邮箱缺@）
```

**视觉效果增强：** 从"仅数字错误"扩展到邮箱、日期、电话、URL等多种格式错误，视觉特征更丰富

---

### 8. Style_Color_Contrast (颜色对比度)
**当前实现：**
- 做法：将文本色设为背景色，opacity=0.6。
- 可见效果：文字几乎不可见。
- 约束：bbox不变。

**视觉特征随机性：** ❌ 极低
**训练数据质量：** ⭐⭐ 偏低 - 过于极端

**视觉模型视角的问题：**
- ❌ 问题1：直接用背景色导致文字**完全不可见**，这不是"对比度不足"而是"消失"（与Element_Missing重复）
- ❌ 问题2：真实的对比度问题是"难以阅读"而非"看不见"，当前实现过于极端
- ❌ 问题3：固定opacity=0.6，无随机性
- ⚠️ 问题4：背景色解析可能失败（渐变、图片），导致注入无效

**改进方案（真实的对比度不足）：**
```python
# 方案1：使用HSL色彩空间生成"相近色"（而非相同色）
script = """
(function(el) {
    const cs = window.getComputedStyle(el);
    function rgbToHsl(r, g, b) {
        r /= 255; g /= 255; b /= 255;
        const max = Math.max(r, g, b), min = Math.min(r, g, b);
        let h, s, l = (max + min) / 2;
        if (max === min) {
            h = s = 0;
        } else {
            const d = max - min;
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            switch(max) {
                case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
                case g: h = ((b - r) / d + 2) / 6; break;
                case b: h = ((r - g) / d + 4) / 6; break;
            }
        }
        return [h * 360, s * 100, l * 100];
    }
    
    const bgMatch = cs.backgroundColor.match(/\\d+/g);
    if (!bgMatch || bgMatch.length < 3) {
        // 背景色解析失败，使用默认浅灰
        el.style.color = '#ccc';
        return;
    }
    
    const [r, g, b] = bgMatch.map(Number);
    let [h, s, l] = rgbToHsl(r, g, b);
    
    // 生成相近亮度的颜色（亮度差仅10-25）
    const lightness_diff = %s;  // Python随机生成10-25
    let text_l = l + lightness_diff;
    if (text_l > 100) text_l = l - lightness_diff;
    if (text_l < 0) text_l = 10;
    
    el.style.color = `hsl(${h}, ${s}%, ${text_l}%)`;
    el.style.textShadow = 'none';
    // 视觉特征：文字与背景颜色相近，需仔细辨认
})(arguments[0]);
""" % random.randint(10, 25)

# 方案2：预定义的低对比度组合（更可控）
low_contrast_pairs = [
    ('#f0f0f0', '#d0d0d0'),  # 浅灰+更浅灰
    ('#2a2a2a', '#404040'),  # 深灰+更深灰
    ('#fff', '#e8e8e8'),     # 白+浅灰
    ('#000', '#333'),        # 黑+深灰
    ('#ffe0e0', '#ffc0c0'),  # 浅粉+粉色
]
bg_color, text_color = random.choice(low_contrast_pairs)
script = f"""
arguments[0].style.backgroundColor = '{bg_color}';
arguments[0].style.color = '{text_color}';
arguments[0].style.textShadow = 'none';
"""
# 视觉特征：文字模糊、难以阅读，但并非完全不可见

# 方案3：随机opacity（而非固定0.6）
opacity = random.uniform(0.3, 0.75)
script += f"arguments[0].style.opacity = '{opacity}';"
```

**视觉效果增强：** 从"完全不可见"改为"对比度不足、难以辨认"，更贴近真实bug的视觉特征

---

### 9. Style_Size_Inconsistent (尺寸不一致)
**当前实现：**
- 做法：scale(0.75-1.3) + width随机化。
- 可见效果：元素尺寸突变。
- 约束：可能改变bbox。

**视觉特征随机性：** ⭐⭐⭐ 良好
**训练数据质量：** ⭐⭐⭐ 中等 - 缺少对比参照

**视觉模型视角的问题：**
- ⚠️ 问题1：单个元素尺寸变化，缺少参照物，模型难以判断"不一致"（需要对比同级元素）
- ⚠️ 问题2：同Layout_Alignment问题，"不一致"必须有对比才能在视觉上识别
- ✅ scale和width修改会产生视觉差异，但需要同级对比

**改进方案（增加视觉对比）：**
```python
# ⚠️ 关键："不一致"必须在对比中体现！

# 方案1：找到同级元素，只修改目标元素（其他作为参照）
siblings = driver.execute_script("""
    const parent = arguments[0].parentElement;
    const tag = arguments[0].tagName;
    return Array.from(parent.children).filter(el => 
        el.tagName === tag &&  // 同类元素（如都是button）
        el !== arguments[0] && 
        el.offsetHeight > 15
    );
""", element)

if len(siblings) >= 1:  # 至少有一个同级作为参照
    # 只修改目标元素尺寸
    scale_factor = random.choice([0.6, 0.7, 1.4, 1.6, 1.8])  # 明显差异
    script = f"""
    const el = arguments[0];
    el.style.transform = 'scale({scale_factor})';
    el.style.transformOrigin = 'center center';
    el.style.display = 'inline-block';
    """
    # 视觉特征：一排按钮中某个特别大/小
    
# 方案2：修改字体大小（视觉上更直观）
if element.tag_name.lower() in ['p', 'span', 'a', 'button', 'h1', 'h2', 'h3']:
    current_size = element.value_of_css_property('font-size')
    size_px = int(current_size.replace('px', ''))
    new_size = size_px * random.choice([0.5, 0.7, 1.5, 2.0])
    script = f"arguments[0].style.fontSize = '{int(new_size)}px';"
    # 视觉特征：文字大小突变

# 方案3：增加行高错误（视觉上是垂直间距异常）
script += f"arguments[0].style.lineHeight = '{random.choice([0.8, 2.5, 3.0])}';"
# 视觉特征：文字行间距过大或文字重叠

# 方案4：记录同级元素bbox（用于训练对比识别）
if siblings:
    sibling_bboxes = [
        driver.execute_script("return arguments[0].getBoundingClientRect();", sib)
        for sib in siblings[:3]  # 最多记录3个
    ]
    label_data['reference_bboxes'] = sibling_bboxes  # 添加到元数据
    # 模型可学习：目标元素与参照元素的尺寸比例异常
```

**视觉效果增强：** 必须包含同级参照元素，增加字体大小、行高等直观的视觉差异

---

## 综合改进优先级（视觉模型视角）

### 🔴 高优先级（严重影响视觉识别）
1. **Layout_Overlap** - 固定偏移量导致过拟合，需增加视觉多样性
2. **Style_Color_Contrast** - 当前过于极端（文字消失），需改为真实的低对比度
3. **Text_Overflow** - 固定字符串、单一方向，视觉模式单一

### 🟡 中优先级（视觉场景受限）
4. **Data_Format_Error** - 适用场景太少，需扩展到多种输入类型
5. **Layout_Alignment** - 需要同级元素对比，否则无法判断"不对齐"
6. **Style_Size_Inconsistent** - 需要参照元素形成视觉对比
7. **Broken_Image** - 视觉特征依赖浏览器，需增加可控的视觉表现

### 🟢 低优先级（视觉特征已清晰）
8. **Element_Missing** - 可增加多种消失模式（空白/重排/透明），但当前已可用
9. **Layout_Spacing** - 实现较好，可增加水平间距和负值场景

## 视觉模型训练的数据增强建议

### 必须注意的视觉特征
1. **对比上下文**
   - ❌ 错误：孤立地修改元素，模型无参照物
   - ✅ 正确：保留同级元素作为参照，制造"不一致对比"
   - 适用：Layout_Alignment, Style_Size_Inconsistent, Layout_Spacing

2. **视觉可区分性**
   - ❌ 错误：不同代码实现产生相同截图效果
   - ✅ 正确：确保每种bug类型有独特的视觉特征
   - 示例：Element_Missing的三种消失方式视觉不同

3. **多样性 > 数量**
   - ❌ 错误：生成1000张"±50px偏移"的重复样本
   - ✅ 正确：生成覆盖不同偏移比例、方向、遮挡的多样样本
   - 目标：让模型学会泛化，而非记忆特定数值

4. **难样本覆盖**
   - 轻微错误：10px小偏移、轻微溢出、1.1x尺寸差异
   - 极端错误：严重重叠、完全溢出、5x尺寸差异
   - 边界情况：部分在视口外、透明元素、背景色冲突

### 元数据增强（便于模型学习）
```python
label_data = {
    "id": pair_id,
    "bug_type": info['type'],
    "bbox_before": normal_bbox,
    "bbox_after": buggy_bbox,
    
    # 新增：视觉特征描述
    "visual_features": {
        "severity": random.choice(['mild', 'moderate', 'severe']),  # 错误严重程度
        "has_reference": bool(siblings),  # 是否有参照元素
        "reference_bboxes": sibling_bboxes if siblings else [],  # 参照元素位置
        "affected_area_ratio": (buggy_bbox['width'] * buggy_bbox['height']) / (VIEWPORT_SIZE[0] * VIEWPORT_SIZE[1]),  # 影响区域占比
        "visual_saliency": "high/low",  # 视觉显著性（红色vs灰色）
    },
    
    # 新增：元素上下文（帮助理解场景）
    "element_context": {
        "tag": element.tag_name.lower(),
        "has_text": bool(element.text.strip()),
        "has_image": element.tag_name.lower() == 'img',
        "parent_tag": element.parent.tag_name.lower() if element.parent else None,
        "sibling_count": len(siblings),
    }
}
```

### 样本平衡策略
- 当前：随机选择bug类型，可能导致分布不均
- 改进：每种类型生成固定数量，确保训练平衡
- 或：根据bug类型的识别难度加权采样（难样本多生成）

## 调试与稳定性策略
- Red overlay：只在截图瞬间绘制，避免元素本身添加红框；注入后重取 bbox 使红框跟随重排后的真实位置。
- 动画/过渡禁用：减少轮播/滑块/渐变导致的位移。
- 不稳定区域过滤：跳过含广告/轮播关键词的元素，降低节点被替换或滑动的概率。
- 视口锁定：注入前后滚动位置一致，利于 diff 计算与模型训练。
- 失败重试：每个 URL 最多 3 次尝试，失败则刷新页面继续下一个样本。

## 运行
- 入口：直接运行 `python auto_injector.py`。
- 配置：调整顶部的 `DEBUG_MODE`、`TARGET_URLS`、`VIEWPORT_SIZE`、输出目录等。
- 产物：
  - `dataset_injected/images/*_normal.png` 与 `*_buggy.png`
  - `dataset_injected/metadata/<id>.json`（包含 bbox 前后、归一化坐标、diff_score、scroll_y 等）

如需进一步增强特定缺陷的可视效果，可适当调大数值范围（如 Layout_Alignment 偏移或 Layout_Spacing 外边距增量），或在注入后增加等待时间。