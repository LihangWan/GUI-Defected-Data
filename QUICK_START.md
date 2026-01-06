# WebArena-Inspired Data Injection - 快速开始指南

## 🚀 30 秒快速开始

### 1️⃣ 安装依赖
```bash
pip install -r requirements.txt
```

### 2️⃣ 启动本地 Web 应用
```bash
docker-compose up -d
```
等待 60-120 秒让容器完全启动。

### 3️⃣ 验证环境
```bash
python verify_environment.py
```
如果所有检查都 ✅ 通过，说明环境配置成功。

### 4️⃣ 采集数据
```bash
# 采集 50 个样本（视觉 + 交互）
python run_webarena_injector.py --mode both --samples 50

# 或者只采集特定类型
python run_webarena_injector.py --mode visual --samples 30    # 视觉错误
python run_webarena_injector.py --mode interaction --samples 30  # 交互错误
```

采集的数据会保存到 `dataset_injected/` 目录。

---

## 📁 文件结构

```
.
├── docker-compose.yml              # 🐳 本地应用配置（Juice Shop + WordPress）
├── requirements.txt                # 📦 Python 依赖列表
├── verify_environment.py           # ✅ 环境验证脚本
├── run_webarena_injector.py        # 🎯 主注入脚本
├── feature_detector.py             # 🔍 页面特征检测
├── js_network_injector.py          # 🌐 网络拦截模块
├── auto_injector.py                # 📷 视觉类错误采集（原有）
├── interaction_injector.py         # 🖱️ 交互类错误采集（原有，需更新）
├── templates.py                    # 📝 自然语言模板（原有）
├── WEBARENA_GUIDE.md               # 📖 详细文档
└── QUICK_START.md                  # ⚡ 本文件

dataset_injected/                   # 📊 输出数据集（自动创建）
├── images/
│   ├── visual/                     # 视觉类错误图片
│   └── interaction/                # 交互类错误图片
├── labels/                         # 标签 JSON 文件
├── raw_metadata/                   # 原始元数据
└── training_data/
    └── train_sft.jsonl             # SFT 训练数据
```

---

## 💡 工作原理

### 核心改进：3 个新模块

| 模块 | 功能 | 解决的问题 |
|------|------|----------|
| **feature_detector.py** | 自动扫描页面元素，推断页面类型，决定可注入的 Bug | ✅ 解决"在静态页注入表单错误"的问题 |
| **js_network_injector.py** | 用 JavaScript 劫持 `fetch`/`XMLHttpRequest`，模拟网络故障 | ✅ 解决 CDP 崩溃，改用应用层拦截 |
| **run_webarena_injector.py** | 整合以上两个模块，针对本地应用进行批量采集 | ✅ 简化工作流程 |

### 数据采集流程

```
1. 初始化 Selenium WebDriver
2. 访问目标 URL
   ├─ 2.1 特征检测：扫描表单、输入框、按钮
   ├─ 2.2 页面分类：static / form_heavy / interactive / ecommerce
   └─ 2.3 Bug 决策：根据页面类型推荐可注入的 Bug
3. 根据 Bug 类型注入故障
   ├─ 3.1 视觉类：修改 DOM（改变布局、删除元素、改文本）→ 截图
   ├─ 3.2 交互类：拦截网络请求（延迟/错误）→ 记录日志 + 截图
4. 生成数据
   ├─ 4.1 保存前后对比截图
   ├─ 4.2 记录元数据（URL、Bug 类型、页面特征等）
   └─ 4.3 生成自然语言标注（NLP 模板）
5. 输出到 dataset_injected/
```

---

## 🎯 本地应用说明

### OWASP Juice Shop (http://localhost:3000)

**特点**：电商应用，有大量表单、验证逻辑、购物流程

**适合采集的 Bug 类型**：
- ✅ Validation_Error（输错密码、邮箱格式不对、数量填负数）
- ✅ Unexpected_Task_Result（支付失败、库存不足）
- ✅ Silent_Failure（加入购物车失败无反馈）

**推荐采集步骤**：
1. 浏览产品页（无表单 → Navigation_Error）
2. 注册账号（有表单 → Validation_Error）
3. 结账（支付 → Unexpected_Task_Result）

### WordPress (http://localhost:8080)

**特点**：CMS 应用，有评论、发布、后台管理表单

**适合采集的 Bug 类型**：
- ✅ Validation_Error（发布文章时的字段验证）
- ✅ Operation_No_Response（评论发布无反馈）
- ✅ Timeout_Hang（后台加载超时）

**推荐采集步骤**：
1. 浏览博客文章（只读 → 少Bug）
2. 发表评论（有表单 → Validation_Error）
3. 登录后台（认证表单 → Validation_Error）

---

## 🔧 常见问题

### Q: 为什么容器启动很慢？
**A**: 首次拉取镜像需要时间。可以预先拉取：
```bash
docker pull bkimminich/juice-shop:latest
docker pull wordpress:latest
docker pull mysql:8.0
```

### Q: 如何查看容器日志？
```bash
docker-compose logs -f juice-shop      # Juice Shop 日志
docker-compose logs -f wordpress       # WordPress 日志
docker-compose logs -f wordpress-db    # MySQL 日志
```

### Q: 如何停止容器？
```bash
docker-compose down          # 停止并移除容器
docker-compose down -v       # 同时删除数据卷
```

### Q: 如何调试注入过程？
```bash
# 启用调试模式（显示浏览器窗口）
python run_webarena_injector.py --mode visual --debug --samples 5

# 查看详细日志
python run_webarena_injector.py --mode both --samples 10 2>&1 | tee injection.log
```

### Q: 采集的数据在哪里？
```
dataset_injected/
├── images/
│   ├── visual/          # 视觉错误图片
│   └── interaction/     # 交互错误图片
├── labels/              # JSON 标签
└── raw_metadata/        # 元数据和日志
```

---

## 📊 预期输出

成功采集 50 个样本后，你会看到：

```
📈 COLLECTION SUMMARY
============================================================
Visual samples:       30
Interaction samples:  20
Total samples:        50
URLs processed:       2/2
Failed URLs:          0
Time elapsed:         245.32s
Output directory:     dataset_injected
============================================================
```

每个样本包含：
- **图片**：`visual_<uuid>.png` 或 `interaction_<uuid>.png`
- **标签**：`visual_<uuid>.json` 或 `interaction_<uuid>.json`
- **元数据**：URL、Bug 类型、页面特征、时间戳等

---

## 🚀 下一步

1. **调整采集参数**：
   - 修改 `--samples` 增加/减少样本数
   - 修改 `run_webarena_injector.py` 中的权重来改变 Bug 分布

2. **自定义 Bug 类型**：
   - 编辑 `feature_detector.py` 的 `get_allowed_bugs()` 方法
   - 编辑 `js_network_injector.py` 添加新的拦截模式

3. **集成到 MLLM 训练**：
   - 使用 `dataset_injected/training_data/train_sft.jsonl` 训练模型
   - 参考 `templates.py` 的自然语言模板生成逻辑

4. **性能优化**：
   - 并行采集（多个 WebDriver 实例）
   - 缓存页面特征以加速重复采集

---

## 📚 参考资源

- [WebArena 论文](https://webarena.dev/)
- [OWASP Juice Shop](https://owasp.org/www-project-juice-shop/)
- [Selenium 文档](https://www.selenium.dev/)
- [Docker 文档](https://docs.docker.com/)

---

## 💬 反馈

如遇问题，请查阅 `WEBARENA_GUIDE.md` 或运行 `verify_environment.py` 诊断环境。

**祝你数据采集顺利！** 🎉
