import os

# Output paths
OUTPUT_DIR = "dataset_injected"
IMG_INTERACTION_DIR = os.path.join(OUTPUT_DIR, "images", "interaction")
META_DIR = os.path.join(OUTPUT_DIR, "raw_metadata")

# Browser / viewport
VIEWPORT_SIZE = (1920, 1080)

# Link discovery
LINK_DISCOVERY_LIMIT = 8
LINK_SAMPLES_PER_PAGE = 3

# Sampling defaults
DEFAULT_SAMPLES_PER_SITE = 6
DEFAULT_LINK_SAMPLES = LINK_SAMPLES_PER_PAGE

# Target sites with routes (deep traversal)
TARGETS = {
    "juice_shop": {
        "base": "http://localhost:3000",
        "routes": [
            # 认证相关 (有登录/注册表单)
            "/#/login",
            "/#/register",
            "/#/forgot-password",
            # 购物功能 (有按钮、数量输入)
            "/#/search",
            "/#/basket",
            "/#/address/select",
            "/#/delivery-method",
            "/#/payment/shop",
            # 用户交互表单
            "/#/contact",
            "/#/complain",
            "/#/chatbot",
            "/#/track-result",
            "/#/recycle",
            "/#/deluxe-membership",
            # 个人中心 (需要登录但页面本身有表单)
            "/#/privacy-security/change-password",
            "/#/privacy-security/two-factor-authentication",
            "/#/wallet",
            "/#/order-history",
            "/#/address/saved",
            "/#/saved-payment-methods",
            # 其他交互页面
            "/#/about",
            "/#/photo-wall",
            "/#/score-board",
        ],
        "auth_required": False,
    },
    "wordpress": {
        "base": "http://localhost:8080",
        "routes": ["/wp-login.php", "/wp-admin/", "?s=test", "/wp-admin/post-new.php"],
        "auth_required": False,
    },
    # Extend here (e.g., odoo, mattermost, nodebb, prestashop, bookstack)
}
