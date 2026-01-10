# 🚀 快速使用指南

## 问题修复概览

| 问题 | 状态 | 解决方案 |
|-----|------|--------|
| 红标显示 | ✅ 已修复 | 改进 `capture.py` 中的绘制逻辑 |
| 无法确认注入 | ✅ 已修复 | 添加详细日志和 `injection_verified` 字段 |

## 快速开始

### 1️⃣ 启动测试服务（可选）
```bash
docker-compose up -d
```

### 2️⃣ 生成样本（5-10分钟）
```bash
# 在项目根目录运行
python quick_sample_generator.py
```

**输出内容**:
```
🚀 快速样本生成器 - Bug注入效果检查
===============================================

[*] 启动注入引擎（调试模式）
[*] 开始生成样本...
    配置:
    • 每个页面: 6 个样本
    • 启用网络拦截: 是
    • 启用可视化: 是
    • 调试模式: 是 (加快执行)

  [Action] Overlay visualized: Timeout_Hang
  [Execute] Bug type: timeout → Timeout_Hang
  [Inject] Timeout_Hang: ✓ Injected
  ...

📊 生成样本统计 (共 6 个)
===============================================
  int_abc123_start.png
    ├─ Bug类型: Timeout_Hang
    ├─ 状态: ✓ 已验证
    ├─ URL: http://localhost:3000
    ...
```

### 3️⃣ 检查质量
```bash
python check_samples.py
```

**输出内容**:
```
🔍 样本质量检查工具
===============================================

📸 图片检查
  ✓ int_abc123: 完整 (start, action, end)
       [✓] 红标检测: 找到 150 个红色像素
  ✓ int_def456: 完整
       [✓] 红标检测: 找到 142 个红色像素
  ...

📋 元数据检查
  ✓ int_abc123.json
       Bug: Timeout_Hang           ✓ 已验证
       图片: ✓ 3张完整
  ...

✅ 完整度: 6/6
📊 Bug类型分布:
  • Navigation_Error: 1
  • Timeout_Hang: 2
  • Operation_No_Response: 1
  • Validation_Error: 1
  • Unexpected_Task_Result: 1

🔍 Bug注入质量检查
int_abc123.json:
  [✓] 网络拦截: 1 条日志
  [✓] 描述: Network latency simulated (15s)...
  [✓] 目标元素: "Login"
  [✓] 点击坐标: (960, 540)
```

## 📂 输出文件位置

```
dataset_injected/
├── images/interaction/
│   ├── int_abc123_start.png   # 初始页面
│   ├── int_abc123_action.png  # 带红标和指针
│   ├── int_abc123_end.png     # 点击后的页面
│   ├── int_def456_start.png
│   ├── int_def456_action.png
│   └── int_def456_end.png
├── raw_metadata/
│   ├── int_abc123.json        # 元数据（包含injection_verified）
│   └── int_def456.json
└── labels/
```

## 🔍 关键验证点

### ✅ 图片检查
- [ ] 打开 `dataset_injected/images/interaction/*_action.png`
- [ ] 确认**右上角**有**清晰的红标**
- [ ] 确认中间有**白色指针**指向点击位置

### ✅ 元数据检查
```bash
# 查看任一JSON文件
cat dataset_injected/raw_metadata/int_abc123.json | jq .

# 关键字段:
# - "injection_verified": true   ← 必须为true
# - "interceptor_logs": [...]    ← 应该有内容
# - "bug_type": "Timeout_Hang"   ← 应该是有效的bug类型
# - "element_semantic": {...}    ← 应该包含元素信息
```

## 🐛 6种Bug类型和验证方式

| # | Bug类型 | 验证方式 | 日志输出 |
|---|--------|--------|--------|
| 1 | `Navigation_Error` | 控制台日志 + 导航日志 | `[Inject] Navigation_Error: ✓ Injected` |
| 2 | `Timeout_Hang` | 拦截器延迟日志 | `[Inject] Timeout_Hang: ✓ Injected` |
| 3 | `Operation_No_Response` | 拦截器超时日志 | `[Inject] Operation_No_Response: ✓ Injected` |
| 4 | `Validation_Error` | 自动（表单验证） | `[Inject] Validation_Error: ✓ Injected` |
| 5 | `Unexpected_Task_Result` | 拦截器错误日志 | `[Inject] Unexpected_Task_Result: ✓ Injected` |
| 6 | `Silent_Failure` | 拦截器日志 | `[Inject] Silent_Failure: ✓ Injected` |

## ⚙️ 如果需要调整

### 修改样本数量
编辑 `quick_sample_generator.py` 第 100 行:
```python
injector.run_batch(
    targets,
    samples_per_site=10,  # ← 改成你需要的数量（默认6）
    ...
)
```

### 修改红标颜色
编辑 `interaction_engine/capture.py` 第 15 行:
```python
fill=(239, 68, 68, 240),  # ← RGB颜色值，当前为红色
# 想要更亮: (255, 70, 70, 255)
# 想要更深: (220, 50, 50, 240)
```

### 修改超时时间
编辑 `interaction_engine/injectors.py` 第 367 行:
```python
self.js_interceptor.set_global_delay(15000)  # ← 毫秒，默认15秒
```

## 🆘 常见问题

**Q: 红标看不清？**
- A: 检查图片是否真的保存了（check_samples.py会检查）
- 可能需要调整色值，看 ⚙️ 部分

**Q: injection_verified=false？**
- A: 可能是拦截器没有正确注入，检查浏览器控制台是否有错误
- 增加 sleep 时间让网络拦截有时间生效

**Q: 完全没有图片或元数据？**
- A: 确保服务器运行中（docker-compose up）
- 检查 Chrome/Chromium 是否安装

**Q: 脚本运行太慢？**
- A: 这是正常的，selenium需要时间加载页面和注入JS
- 可以在 config.py 中调整超时时间

## 📞 更多信息

查看详细文档: [FIXES_SUMMARY.md](FIXES_SUMMARY.md)

祝您样本生成顺利！ 🎉
