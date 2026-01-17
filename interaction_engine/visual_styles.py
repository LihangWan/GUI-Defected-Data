"""
多样化视觉样式模板 - 防止模型过拟合

每种 Bug 类型提供多种视觉样式，随机选择以增加数据多样性。
"""
import random

# ============================================================================
# Navigation_Error (404) 样式模板
# ============================================================================
ERROR_404_STYLES = [
    # 样式 1: 深蓝科技风
    {
        "name": "tech_dark",
        "body_style": """
            margin: 0; padding: 0; min-height: 100vh;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            display: flex; justify-content: center; align-items: center;
            font-family: 'Segoe UI', Tahoma, sans-serif;
        """,
        "code_style": "font-size: 180px; font-weight: 900; color: #e94560; text-shadow: 0 0 40px rgba(233,69,96,0.5);",
        "title_style": "font-size: 36px; color: #fff; font-weight: 300;",
        "desc_color": "#a0a0a0",
        "error_box_bg": "rgba(233, 69, 96, 0.1)",
        "error_box_border": "rgba(233, 69, 96, 0.3)",
    },
    # 样式 2: 白色简约风
    {
        "name": "minimal_white",
        "body_style": """
            margin: 0; padding: 0; min-height: 100vh;
            background: #f5f5f5;
            display: flex; justify-content: center; align-items: center;
            font-family: Arial, sans-serif;
        """,
        "code_style": "font-size: 200px; font-weight: 100; color: #333; letter-spacing: -10px;",
        "title_style": "font-size: 24px; color: #666; font-weight: 400; text-transform: uppercase; letter-spacing: 5px;",
        "desc_color": "#999",
        "error_box_bg": "#fff",
        "error_box_border": "#ddd",
    },
    # 样式 3: 红色警告风
    {
        "name": "red_warning",
        "body_style": """
            margin: 0; padding: 0; min-height: 100vh;
            background: linear-gradient(180deg, #ff4444 0%, #cc0000 100%);
            display: flex; justify-content: center; align-items: center;
            font-family: 'Helvetica Neue', sans-serif;
        """,
        "code_style": "font-size: 160px; font-weight: bold; color: #fff; text-shadow: 3px 3px 0 rgba(0,0,0,0.2);",
        "title_style": "font-size: 32px; color: #fff; font-weight: 600;",
        "desc_color": "rgba(255,255,255,0.8)",
        "error_box_bg": "rgba(0, 0, 0, 0.2)",
        "error_box_border": "rgba(255, 255, 255, 0.3)",
    },
    # 样式 4: 灰色工业风
    {
        "name": "industrial_gray",
        "body_style": """
            margin: 0; padding: 0; min-height: 100vh;
            background: #2c2c2c;
            display: flex; justify-content: center; align-items: center;
            font-family: 'Courier New', monospace;
        """,
        "code_style": "font-size: 150px; font-weight: normal; color: #ff6600; font-family: 'Courier New', monospace;",
        "title_style": "font-size: 28px; color: #ccc; font-weight: normal; font-family: 'Courier New', monospace;",
        "desc_color": "#888",
        "error_box_bg": "#333",
        "error_box_border": "#555",
    },
    # 样式 5: 蓝色企业风
    {
        "name": "corporate_blue",
        "body_style": """
            margin: 0; padding: 0; min-height: 100vh;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex; justify-content: center; align-items: center;
            font-family: 'Segoe UI', sans-serif;
        """,
        "code_style": "font-size: 170px; font-weight: 800; color: #fff; opacity: 0.9;",
        "title_style": "font-size: 30px; color: #fff; font-weight: 300;",
        "desc_color": "rgba(255,255,255,0.7)",
        "error_box_bg": "rgba(255, 255, 255, 0.15)",
        "error_box_border": "rgba(255, 255, 255, 0.3)",
    },
]

# ============================================================================
# Operation_No_Response (Loading/Timeout) 样式模板
# ============================================================================
LOADING_STYLES = [
    # 样式 1: 标准白色 Spinner
    {
        "name": "standard_white",
        "overlay_bg": "rgba(0, 0, 0, 0.5)",
        "box_bg": "rgba(255, 255, 255, 0.95)",
        "spinner_border": "#e0e0e0",
        "spinner_active": "#3498db",
        "text_color": "#333",
        "text": "Loading...",
    },
    # 样式 2: 深色主题
    {
        "name": "dark_theme",
        "overlay_bg": "rgba(0, 0, 0, 0.7)",
        "box_bg": "rgba(30, 30, 30, 0.95)",
        "spinner_border": "#444",
        "spinner_active": "#00bcd4",
        "text_color": "#fff",
        "text": "Please wait...",
    },
    # 样式 3: 毛玻璃效果
    {
        "name": "glass_blur",
        "overlay_bg": "rgba(255, 255, 255, 0.3)",
        "box_bg": "rgba(255, 255, 255, 0.8)",
        "spinner_border": "#ddd",
        "spinner_active": "#2196f3",
        "text_color": "#333",
        "text": "Loading data...",
        "extra_style": "backdrop-filter: blur(10px);",
    },
    # 样式 4: 红色警告
    {
        "name": "warning_red",
        "overlay_bg": "rgba(200, 0, 0, 0.3)",
        "box_bg": "rgba(255, 255, 255, 0.95)",
        "spinner_border": "#ffcccc",
        "spinner_active": "#ff4444",
        "text_color": "#c00",
        "text": "Processing...",
    },
    # 样式 5: 绿色进度
    {
        "name": "progress_green",
        "overlay_bg": "rgba(0, 0, 0, 0.4)",
        "box_bg": "#fff",
        "spinner_border": "#c8e6c9",
        "spinner_active": "#4caf50",
        "text_color": "#2e7d32",
        "text": "Connecting...",
    },
]

# ============================================================================
# Unexpected_Task_Result (Error Toast) 样式模板
# ============================================================================
ERROR_TOAST_STYLES = [
    # 样式 1: 红色渐变
    {
        "name": "gradient_red",
        "position": "top",
        "bg": "linear-gradient(135deg, #d32f2f 0%, #b71c1c 100%)",
        "text_color": "#fff",
        "title": "Error 500: Internal Server Error",
        "message": "The server encountered an unexpected condition.",
        "icon_color": "#fff",
    },
    # 样式 2: 橙色警告
    {
        "name": "warning_orange",
        "position": "top",
        "bg": "linear-gradient(135deg, #ff9800 0%, #f57c00 100%)",
        "text_color": "#fff",
        "title": "Server Error",
        "message": "Request failed. Please try again later.",
        "icon_color": "#fff",
    },
    # 样式 3: 底部深色
    {
        "name": "dark_bottom",
        "position": "bottom",
        "bg": "#333",
        "text_color": "#fff",
        "title": "Request Failed",
        "message": "HTTP 500 - Internal Server Error",
        "icon_color": "#ff5252",
    },
    # 样式 4: Material Design 风格
    {
        "name": "material_snackbar",
        "position": "bottom",
        "bg": "#323232",
        "text_color": "#fff",
        "title": "Error",
        "message": "Something went wrong. Error code: 500",
        "icon_color": "#ff5252",
    },
    # 样式 5: 全屏遮罩错误
    {
        "name": "fullscreen_error",
        "position": "center",
        "bg": "rgba(0,0,0,0.85)",
        "text_color": "#fff",
        "title": "500 Internal Server Error",
        "message": "The server was unable to complete your request.",
        "icon_color": "#f44336",
    },
]


def get_random_404_style():
    """随机获取一个 404 页面样式"""
    return random.choice(ERROR_404_STYLES)


def get_random_loading_style():
    """随机获取一个 Loading 样式"""
    return random.choice(LOADING_STYLES)


def get_random_error_toast_style():
    """随机获取一个 Error Toast 样式"""
    return random.choice(ERROR_TOAST_STYLES)


def generate_404_page_js(style: dict = None) -> str:
    """生成 404 页面的 JavaScript 代码"""
    if style is None:
        style = get_random_404_style()
    
    return f"""
        (function() {{
            document.body.innerHTML = '';
            document.body.style.cssText = `{style['body_style']}`;
            
            const container = document.createElement('div');
            container.style.cssText = 'text-align: center; padding: 40px;';
            
            const errorCode = document.createElement('div');
            errorCode.textContent = '404';
            errorCode.style.cssText = `{style['code_style']} line-height: 1; margin-bottom: 20px;`;
            
            const title = document.createElement('h1');
            title.textContent = 'Page Not Found';
            title.style.cssText = `{style['title_style']} margin: 0 0 15px 0;`;
            
            const desc = document.createElement('p');
            desc.textContent = 'The page you are looking for might have been removed or is temporarily unavailable.';
            desc.style.cssText = `font-size: 16px; color: {style['desc_color']}; max-width: 500px; margin: 0 auto 30px auto; line-height: 1.6;`;
            
            const errorBox = document.createElement('div');
            errorBox.style.cssText = `background: {style['error_box_bg']}; border: 1px solid {style['error_box_border']}; border-radius: 8px; padding: 15px 25px; display: inline-block;`;
            errorBox.innerHTML = '<span style="color: {style.get("error_text_color", "#e94560")}; font-weight: 600;">Error:</span> <span style="color: {style.get("desc_color", "#fff")};">Navigation failed</span>';
            
            container.appendChild(errorCode);
            container.appendChild(title);
            container.appendChild(desc);
            container.appendChild(errorBox);
            document.body.appendChild(container);
            
            document.title = '404 - Page Not Found';
            console.log('[ICE] 404 page injected with style: {style["name"]}');
        }})();
    """


def generate_loading_overlay_js(style: dict = None) -> str:
    """生成 Loading 遮罩的 JavaScript 代码"""
    if style is None:
        style = get_random_loading_style()
    
    extra_style = style.get('extra_style', '')
    
    return f"""
        (function() {{
            const existing = document.getElementById('__ICE_LOADING_OVERLAY__');
            if (existing) existing.remove();
            
            const overlay = document.createElement('div');
            overlay.id = '__ICE_LOADING_OVERLAY__';
            overlay.style.cssText = `
                position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                background: {style['overlay_bg']}; z-index: 999999;
                display: flex; justify-content: center; align-items: center;
                pointer-events: all; {extra_style}
            `;
            
            const spinnerBox = document.createElement('div');
            spinnerBox.style.cssText = `
                background: {style['box_bg']}; padding: 30px 40px;
                border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                text-align: center;
            `;
            
            const spinner = document.createElement('div');
            spinner.style.cssText = `
                width: 50px; height: 50px;
                border: 5px solid {style['spinner_border']};
                border-top: 5px solid {style['spinner_active']};
                border-radius: 50%; margin: 0 auto 15px auto;
                animation: ice-spin 1s linear infinite;
            `;
            
            const styleTag = document.createElement('style');
            styleTag.textContent = '@keyframes ice-spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}';
            document.head.appendChild(styleTag);
            
            const text = document.createElement('div');
            text.textContent = '{style["text"]}';
            text.style.cssText = `color: {style['text_color']}; font-size: 16px; font-family: Arial, sans-serif;`;
            
            spinnerBox.appendChild(spinner);
            spinnerBox.appendChild(text);
            overlay.appendChild(spinnerBox);
            document.body.appendChild(overlay);
            
            console.log('[ICE] Loading overlay injected with style: {style["name"]}');
        }})();
    """


def generate_error_toast_js(style: dict = None) -> str:
    """生成 Error Toast 的 JavaScript 代码"""
    if style is None:
        style = get_random_error_toast_style()
    
    # 根据位置设置不同的定位样式
    if style['position'] == 'top':
        position_style = 'top: 20px; left: 50%; transform: translateX(-50%);'
    elif style['position'] == 'bottom':
        position_style = 'bottom: 20px; left: 50%; transform: translateX(-50%);'
    else:  # center
        position_style = 'top: 50%; left: 50%; transform: translate(-50%, -50%); width: 80%; max-width: 500px;'
    
    return f"""
        (function() {{
            const existing = document.getElementById('__ICE_ERROR_TOAST__');
            if (existing) existing.remove();
            
            const toast = document.createElement('div');
            toast.id = '__ICE_ERROR_TOAST__';
            toast.style.cssText = `
                position: fixed; {position_style} z-index: 999999;
                background: {style['bg']}; color: {style['text_color']};
                padding: 16px 32px; border-radius: 8px;
                box-shadow: 0 6px 20px rgba(0,0,0,0.3);
                font-family: 'Segoe UI', Arial, sans-serif; font-size: 15px;
                display: flex; align-items: center; gap: 12px;
                animation: ice-toast-in 0.3s ease-out;
            `;
            
            const styleTag = document.createElement('style');
            styleTag.textContent = '@keyframes ice-toast-in {{ from {{ opacity: 0; transform: translateX(-50%) translateY(-20px); }} to {{ opacity: 1; transform: translateX(-50%) translateY(0); }} }}';
            document.head.appendChild(styleTag);
            
            const icon = document.createElement('div');
            icon.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{style["icon_color"]}" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
            icon.style.cssText = 'display: flex; align-items: center;';
            
            const textContainer = document.createElement('div');
            
            const title = document.createElement('div');
            title.textContent = '{style["title"]}';
            title.style.cssText = 'font-weight: 600; margin-bottom: 4px;';
            
            const detail = document.createElement('div');
            detail.textContent = '{style["message"]}';
            detail.style.cssText = 'font-size: 13px; opacity: 0.9;';
            
            textContainer.appendChild(title);
            textContainer.appendChild(detail);
            
            toast.appendChild(icon);
            toast.appendChild(textContainer);
            document.body.appendChild(toast);
            
            console.log('[ICE] Error toast injected with style: {style["name"]}');
        }})();
    """
