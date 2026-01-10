#!/usr/bin/env python3
"""
为每个样本生成便于肉眼检查的审阅图：
- 上排：start / action / end 三联图
- 下排：start vs end 的差异热图（PIL ImageChops.difference）
- 左上角文字：bug类型、验证状态、元素名、URL
输出：dataset_injected/images/interaction/review/<id>_review.png
"""

import os
import json
from pathlib import Path
from typing import Dict
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageEnhance

OUTPUT_DIR = Path("dataset_injected/images/interaction/review")
META_DIR = Path("dataset_injected/raw_metadata")
ROOT = Path("dataset_injected")

BUG_TIPS: Dict[str, str] = {
    "Navigation_Error": "end 应出现错误/404页面或明显跳转到异常路由。差异热图应大面积变化。",
    "Timeout_Hang": "end 应可见加载动画/转圈/进度条。差异热图有局部动态区域但整体不变。",
    "Operation_No_Response": "点击后界面无反馈，end 与 start 基本一致（差异热图很小）。",
    "Unexpected_Task_Result": "end 可能出现错误弹窗/红色提示。差异热图在提示区域有明显变化。",
    "Silent_Failure": "界面看似成功但内容为空/未更新。差异热图变化较小或集中在交互区域。",
    "Validation_Error": "输入框附近出现红色错误文案/红色边框。差异热图在表单区域明显。",
}


def load_image(rel_path: str) -> Image.Image:
    abs_path = ROOT / rel_path
    return Image.open(abs_path).convert("RGB")


def make_review(meta: Dict) -> Image.Image:
    # 读取三帧
    start_rel = meta.get("images", {}).get("start")
    action_rel = meta.get("images", {}).get("action")
    end_rel = meta.get("images", {}).get("end")
    if not (start_rel and action_rel and end_rel):
        raise ValueError("缺少图片路径")

    start = load_image(start_rel)
    action = load_image(action_rel)
    end = load_image(end_rel)

    # 尺寸统一到宽 1280，高按比例
    target_w = 1280
    def resize_keep_ratio(img: Image.Image) -> Image.Image:
        w, h = img.size
        scale = target_w / float(w)
        return img.resize((target_w, int(h * scale)), Image.LANCZOS)

    start_r = resize_keep_ratio(start)
    action_r = resize_keep_ratio(action)
    end_r = resize_keep_ratio(end)

    # 差异热图（增强对比）
    diff = ImageChops.difference(start_r, end_r)
    diff = ImageEnhance.Brightness(diff).enhance(1.6)
    diff = ImageEnhance.Contrast(diff).enhance(1.8)

    # 拼接画布：上排三张并排，下排差异图
    gap = 12
    top_h = max(start_r.height, action_r.height, end_r.height)
    canvas_w = target_w * 3 + gap * 2
    canvas_h = top_h * 2 + gap
    canvas = Image.new("RGB", (canvas_w, canvas_h), (24, 24, 24))

    # 上排
    x = 0
    canvas.paste(start_r, (x, 0)); x += target_w + gap
    canvas.paste(action_r, (x, 0)); x += target_w + gap
    canvas.paste(end_r, (x, 0))
    # 下排差异
    canvas.paste(diff, (0, top_h + gap))

    # 文字信息
    draw = ImageDraw.Draw(canvas)
    bug = meta.get("bug_type", "Unknown")
    verified = meta.get("injection_verified", False)
    elem = meta.get("element_semantic", {}).get("readable_name", "Unknown")
    url = meta.get("url", "")
    tip = BUG_TIPS.get(bug, "查看 end 是否出现异常视觉反馈")
    status = "已验证" if verified else "未验证"
    header = f"Bug: {bug}  |  状态: {status}  |  元素: {elem}  |  URL: {url}"
    draw.rectangle([0, 0, canvas_w, 40], fill=(0, 0, 0))
    draw.text((12, 10), header, fill=(255, 255, 255))

    # 下排提示
    draw.rectangle([0, top_h + gap, canvas_w, top_h + gap + 32], fill=(0, 0, 0))
    draw.text((12, top_h + gap + 8), f"视觉判定提示：{tip}", fill=(255, 255, 255))

    # 小角标
    def tag(x0: int, y0: int, text: str, color=(239,68,68)):
        tw, th = 160, 30
        draw.rectangle([x0, y0, x0+tw, y0+th], fill=color)
        draw.text((x0+8, y0+7), text[:18], fill=(255,255,255))
    tag(12, 44, "START")
    tag(target_w + gap + 12, 44, "ACTION")
    tag(target_w*2 + gap*2 + 12, 44, "END")
    tag(12, top_h + gap + 40, "DIFF")

    return canvas


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(META_DIR.glob("int_*.json"))
    if not files:
        print("[-] 未找到样本元数据。请先运行 quick_sample_generator.py")
        return

    print(f"[*] 生成审阅图... ({len(files)} 个样本)")
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                meta = json.load(f)
            img = make_review(meta)
            out = OUTPUT_DIR / f"{meta.get('id', fp.stem)}_review.png"
            img.save(out)
            print(f"  ✓ {out.name}")
        except Exception as e:
            print(f"  [!] {fp.name}: {e}")

    print("\n[✓] 完成。请查看 dataset_injected/images/interaction/review/")


if __name__ == "__main__":
    main()
