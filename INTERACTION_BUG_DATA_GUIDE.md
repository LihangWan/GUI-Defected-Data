# 交互类 Bug 注入与数据生成指南

本文档面向使用 `interaction_engine/` 生成交互类（Interaction）GUI Bug 数据的同学，系统性说明：
- 数据类型的选择与结构设计（用于训练多模态 LLM）
- 数据生成的整体思路与流程（原生优先 + 注入兜底）
- 数据质量保障措施（一致性、去重、可验证）
- 后续优化方向（提升质量、扩站点扩规模、增强多样性）

---

## 一、范围与术语
- Big Three 交互类 Bug：
  - Navigation_Error：错误路由/404、跳转异常
  - Operation_No_Response：点击无响应/长时间卡顿
  - Unexpected_Task_Result：错误提示/操作结果不符预期
- 原生优先（Native First）：优先检测并使用网站本身的错误页、加载遮罩、提示组件；若无，则使用我们注入的多样化样式进行兜底。
- 注入（Injection）：通过 Selenium + JS 在被测页面动态插入脚本/CSS，以模拟交互异常、覆盖层、错误提示等。

---

## 二、数据类型与结构设计
交互类数据需要同时服务“感知（视觉）”与“理解（语义）”。为此，建议统一输出到 `dataset_injected/` 下，采用如下多通道结构：

- 图片通道（视觉证据）
  - 路径：`dataset_injected/images/interaction/`
  - 内容：成对截图（before/after），以及必要的局部裁剪（overlay/404/toast 组件区域）
  - 命名包含：站点、页面、采样 ID、Bug 类型、是否原生（native/injected）

- 标签通道（结构化标注）
  - 路径：`dataset_injected/labels/`
  - JSON 字段建议：
    - `bug_type`: `Navigation_Error` | `Operation_No_Response` | `Unexpected_Task_Result`
    - `is_native`: 是否使用原生组件（true/false）
    - `page_url`: 页面 URL
    - `element_selector`: 关键元素的 CSS/XPath（如触发按钮、提示容器）
    - `bboxes`: 关键区域的归一化坐标数组（相对视口 0-1）
    - `screenshots`: 关联到图片通道的文件名（before/after/crops）
    - `evidence`: 额外证据（如控制台/网络拦截摘要）

- 原始元数据（可溯源与再加工）
  - 路径：`dataset_injected/raw_metadata/`
  - 内容：
    - 站点 ID、页面哈希、时间戳、浏览器/视口信息
    - 注入方式（原生检测命中/注入样式 ID）
    - 交互轨迹（点击、等待、导航）
    - 失败原因与重试信息

- 语义通道（SFT 训练数据，可选）
  - 路径：`dataset_injected/training_data/train_sft.jsonl`
  - 内容：面向“对话式”多模态描述，样例结构：
    ```json
    {"id": "site_page_sample", "bug_type": "Operation_No_Response", "is_native": false,
     "messages": [
       {"role": "system", "content": "你是前端测试助手，描述并定位交互异常。"},
       {"role": "user", "content": "请检查截图并说明为什么点击未产生响应。"},
       {"role": "assistant", "content": "在截图右上角的按钮被覆盖于加载遮罩下，点击事件未触发。建议在操作过程中禁用遮罩或增加交互反馈。"}
     ],
     "images": ["images/interaction/.../after.png"],
     "metadata_ref": "raw_metadata/...json"}
    ```

---

## 三、生成思路与流程
整体流程由 `main_interaction.py` 驱动，调用 `interaction_engine/injectors.py` 完成具体注入：

1) 站点与页面采样
- 站点配置来源：`interaction_engine/config.py` 中的 `TARGETS`
- 可选启发式链接发现：受 `LINK_DISCOVERY_LIMIT` 与 `LINK_SAMPLES_PER_PAGE` 控制

2) 原生检测（优先）
- 通过 `NativeErrorPageDetector` 识别：
  - 404/错误页（路由异常组件）
  - 加载覆盖层（loading overlay/spinner）
  - 提示/吐司（toast/snackbar/alert）
- 命中则直接使用原生组件，记录 `is_native=true`，并采集截图与标注

3) 注入兜底（多样化样式）
- 若未命中原生组件，使用 `visual_styles.py` 中预设的多样化样式（至少 5 种）
- 注入内容包括：
  - 路由异常的替代错误页（404）
  - 操作无响应的加载遮罩/冻结模拟
  - 任务结果异常的错误 toast/snackbar
- 所有注入均在可控窗口与时序下执行，完成前后截图采集

4) 证据采集与质量过滤
- `capture.py`：视口锁定 + 成对截图 + 必要局部裁剪
- 视觉变化验证：在交互场景使用可见性/可点击性校验；必要时结合 SSIM/像素 Diff 辅助判定
- 错误与重试策略：失败样本不入库；记录原因以便后续诊断

5) 数据落盘与可复现
- 统一写入上述四类通道，文件名/字段彼此可引用
- 元数据中保存注入方式、样式 ID、检测命中情况

---

## 四、数据质量保障
- 多样性：
  - 原生优先，避免单一模板导致过拟合
  - 样式池多样化（颜色、布局、动效、位置）
  - 多站点、多页面、多元素类型（按钮、链接、表单控件）
- 一致性：
  - 视口锁定；前后截图分辨率一致
  - BBox 坐标归一化（0-1）跨分辨率稳定
- 可验证性：
  - 交互可点击性/可见性检查（DOM + 事件）
  - 可选视觉差异阈值过滤（低变化样本剔除）
  - `verify_bugs.py` 提供回归验证与基本一致性检查
- 去重与清洗：
  - URL + 组件签名 + 样式 ID 组成样本哈希，避免重复
  - 失败与不稳定样本记录于原始元数据，不纳入训练集

---

## 五、使用与运行
1) 启动被测站点（如需）
```bash
docker-compose up -d
```

2) 生成交互类数据（debug 关闭更充分）
```bash
# Windows/Conda 环境示例
set ICE_DEBUG=0
python main_interaction.py
```

3) 验证生成质量
```bash
python verify_bugs.py
```

依赖参考：`requirements.txt`（Selenium、OpenCV、Scikit-Image、Pillow、NumPy 等）

---

## 六、后续优化方向
- 提升质量：
  - 覆盖更多原生组件检测规则（不同框架 UI 体系：Bootstrap、Material UI、Ant Design、Tailwind 等）
  - 增加交互时序变体：慢网速、延迟响应、并发点击、遮罩竞态
  - 事件级证据：拦截/记录关键事件（click、fetch、xhr），生成因果链摘要
  - 人工审核队列：抽样人工验证，形成黄金集与校正策略
- 提升多样性：
  - 跨浏览器与设备：Chrome/Firefox、移动视口（375x667 等）
  - 多语言与主题：浅色/深色主题、不同语言站点
  - 背景复杂度：不同布局密度与复杂度页面
- 扩站点与规模：
  - 本地容器：OWASP Juice Shop、WordPress、Ghost、Strapi、Grafana（含 Demo 页面）、Matomo、Redmine、Taiga
  - 在线 Demo：Swagger UI、React Admin Demo、Django Admin 示例、RealWorld 项目实例
  - 站点接入规范：在 `interaction_engine/config.py` 添加 `TARGETS` 项（基础 URL、登录/跳转钩子、排除路径）
- 训练数据增强：
  - 语义模板扩展：为交互类 Bug 增加更细粒度的对话模版（触发路径、影响范围、修复建议）
  - 因果提示词：强调“操作→反馈→结果”的因果链，减少纯视觉描述的歧义

---

## 七、风险与注意事项
- 合法性：优先使用开源 Demo 或自建站点，避免对第三方生产站点进行注入与抓取
- 稳定性：不同站点的防自动化策略可能导致注入失败，需增加回退与容错
- 隐私与安全：避免采集含敏感信息的页面；样本落盘前做脱敏处理

---

## 八、结语
当前交互类数据生成管线已具备“原生优先 + 多样化兜底 + 可验证”的核心能力。后续重点在于扩大站点覆盖、增强时序与事件证据、构建审核闭环，以持续提升数据质量与训练效果。
