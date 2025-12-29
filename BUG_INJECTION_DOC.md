# 自动缺陷注入脚本说明 (auto_injector.py)

以下为各缺陷类型的实现细节、可见效果、关键约束与调试行为。脚本运行环境默认 `DEBUG_MODE = True`，会在截图时叠加红色调试框（由页面 overlay 绘制，不修改元素本身）。

## 通用机制
- 视口锁定：截图前记录 `scroll_y`，注入后恢复原滚动以保证 normal/buggy 对齐。
- 元素选择：过滤尺寸过小/过大、负坐标、幽灵元素（透明无内容），并跳过不稳定区域（类名/ID 含 carousel/slider/slick/swiper/ad/promo 等）。
- 动画冻结：每次生成前调用 `pause_animations()` 关闭全局 animation/transition，降低重排导致的偏移。
- 调试红框：截图前读取注入后 bbox（失败则用注入前），用 overlay 画红框；截图后移除。
- 差异校验：计算 normal vs buggy 的 RMS 差异，在 DEBUG_MODE 下仍保留全部样本，仅用于监控。

## 缺陷类型细节

### Layout_Overlap
- 做法：给目标元素 `transform: translate(...)`，偏移 ±50px (X) 与 ±40px (Y)，并 `position: relative; z-index: 99999`。
- 可见效果：元素与周围内容重叠、位置错位。
- 约束：更新 bbox 为偏移后的坐标。

### Element_Missing
- 做法：`visibility: hidden` 隐藏目标元素。DEBUG 模式下在原位插入浅红色占位 `<div>`，无边框/无描边，避免双重红框。
- 可见效果：元素消失；调试时淡红块标示原位置。
- 约束：保留原 bbox（隐藏不变形）。

### Text_Overflow
- 做法：写入超长字符串；移除 `maxlength`；设置 `white-space: nowrap; overflow: visible;`。
  - 若是 `input/textarea`：同时扩宽 `minWidth`/`width`（2x~2.5x 原宽）。
  - 非输入：直接修改 `textContent`。
- 可见效果：文字溢出或拉伸，输入框会被撑宽；调试时轻微红色背景（仅 DEBUG）。
- 约束：重取 bbox 记录放大后的尺寸。

### Broken_Image
- 前置：仅对 `<img>` 执行。
- 做法：替换 `src` 为无效链接；保留原宽高；设置 `display: inline-block; border: 1px solid red/gray; object-fit: contain;`。
- 可见效果：图片断裂占位或错误图标，带边框。
- 约束：bbox 不变。

### Layout_Alignment
- 目的：制造对齐不齐（偏移/内边距不当）。
- 跳过：`input/textarea/select`。
- 做法：随机 24–48px 的位移，方式随机选择：
  - paddingLeft / paddingTop（40% 概率走 padding），或
  - marginLeft / marginRight / marginTop。
- 可见效果：标题/块级内容出现明显左右/上下错位。
- 约束：一般不改变自身尺寸，bbox 维持原值。

### Layout_Spacing
- 目的：拉大容器子元素间距。
- 跳过：`input/textarea/select/button/img` 以及子元素 <2 的容器。
- 做法：选取约 50% 子元素，随机 marginTop/marginBottom，增量 20–45px，去除过渡动画。
- 可见效果：列表/卡片纵向间距不均匀或过大。
- 约束：容器 bbox 可能因子项外边距而微调。

### Data_Format_Error
- 目标：数字输入框。
- 若当前元素不是 `input[type=number]`，在页面内另找一个可见的 number 输入。
- 做法：填入非数字值（如 `abcXYZ`, `NaN??`, `###`, `１２３abc`, `error`），并打标 `data-injected='true'`。
- 可见效果：数字框中出现非法字符串。
- 约束：记录被写入的目标框 bbox。

### Style_Color_Contrast
- 目的：降低文本与背景对比度。
- 做法：获取元素背景色，直接将文本色设为同色，附加 `opacity: 0.6`，移除文字阴影。
- 可见效果：文字几乎与背景融为一体，难以辨认。
- 约束：bbox 不变。

### Style_Size_Inconsistent
- 目的：制造尺寸不一致。
- 做法：随机放大/缩小字体与内边距（比如字体 ×0.6~1.4，padding 左右/上下独立调整），移除过渡。
- 可见效果：同级元素出现尺寸突变，行高/对齐异常。
- 约束：可能轻微改变 bbox。

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