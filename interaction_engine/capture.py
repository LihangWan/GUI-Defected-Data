import os
import time
from PIL import Image, ImageDraw, ImageFont
from typing import Tuple

from .config import OUTPUT_DIR, IMG_INTERACTION_DIR


def visualize_action(img_path: str, x: int, y: int, output_path: str | None = None, label: str | None = None) -> str:
    """Overlay a pointer on a screenshot to mark the intended click. Optional label."""
    img = Image.open(img_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Draw Pointer (only if coordinates are valid)
    if x > 0 and y > 0:
        pointer = [
            (x, y),
            (x, y + 24),
            (x + 8, y + 18),
            (x + 14, y + 32),
            (x + 18, y + 30),
            (x + 12, y + 16),
            (x + 24, y + 16),
        ]
        shadow = [(px + 2, py + 2) for px, py in pointer]

        draw.polygon(shadow, fill=(0, 0, 0, 140))
        draw.polygon(pointer, fill=(255, 255, 255, 230), outline=(0, 0, 0, 220))

    # Draw Label (Simulated Overlay) - Red tag in top-right corner
    if label:
        try:
            # Red tag dimensions and positioning
            tag_w = 140
            tag_h = 32
            pad_x, pad_y = 16, 12
            tx = img.width - tag_w - pad_x  # Right-aligned
            ty = pad_y                       # Top position
            
            # Draw red background rectangle with border
            draw.rectangle([tx, ty, tx+tag_w, ty+tag_h], 
                          fill=(239, 68, 68, 240),      # Bright red with slight transparency
                          outline=(220, 53, 53, 255))   # Darker red border
            
            # Draw text in the red tag
            label_text = str(label)[:16]  # Truncate long labels
            draw.text((tx + 8, ty + 7), label_text, fill=(255, 255, 255, 255))
            
        except Exception as e:
            pass

    out = Image.alpha_composite(img, overlay)
    if output_path is None:
        output_path = img_path.replace(".png", "_action.png")
    out.save(output_path)
    return output_path


def ensure_dirs() -> None:
    os.makedirs(IMG_INTERACTION_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "raw_metadata"), exist_ok=True)


def bug_class(bug_type: str) -> str:
    frozen = {"Operation_No_Response", "Timeout_Hang", "Silent_Failure"}
    explicit = {"Unexpected_Task_Result", "Validation_Error"}
    if bug_type in frozen:
        return "Frozen_Unresponsive"
    if bug_type in explicit:
        return "Explicit_Error_Feedback"
    if bug_type == "Navigation_Error":
        return "Navigation_Failure"
    return "Unknown"


def expected_behavior(bug_type: str) -> str:
    mapping = {
        "Operation_No_Response": "Click should complete and receive server response within reasonable time.",
        "Navigation_Error": "Click should navigate to the correct destination without error.",
        "Unexpected_Task_Result": "API call should succeed (200 OK) without server errors.",
        "Timeout_Hang": "Request should complete within 5-10 seconds, not hang indefinitely.",
        "Silent_Failure": "Successful API response should return data; empty response indicates failure.",
        "Validation_Error": "Input should accept valid values and only show errors for invalid data.",
        "Unknown": "Action should complete successfully without errors.",
    }
    return mapping.get(bug_type, "Action should complete successfully.")


def show_overlay(driver, bug_type: str, desc: str) -> None:
    try:
                safe_bug = str(bug_type or "Unknown")
                safe_desc = str(desc or "Injected interaction")
                driver.execute_script(
                        """
                        (function(){
                            const id = '__ICE_BUG_OVERLAY__';
                            let box = document.getElementById(id);
                            if (!box) {
                                box = document.createElement('div');
                                box.id = id;
                                document.body.appendChild(box);
                            }
                            box.innerHTML = '<div style="display:flex;gap:8px;align-items:center; padding:10px 14px; background:rgba(0,0,0,0.78); color:#fff; border-radius:10px; box-shadow:0 4px 14px rgba(0,0,0,0.35); font-family:Arial,sans-serif; font-size:14px;">'
                                + '<span style="font-weight:bold; letter-spacing:0.3px;">ICE Injection</span>'
                                + '<span style="padding:2px 8px; border-radius:6px; background:#ff6b6b; color:#fff; font-weight:bold;">'+String(arguments[0] || 'Unknown')+'</span>'
                                + '<span style="max-width:360px; opacity:0.9;">'+String(arguments[1] || 'Injected interaction')+'</span>'
                                + '</div>';
                            box.style.position = 'fixed';
                            box.style.top = '12px';
                            box.style.right = '12px';
                            box.style.zIndex = 999999;
                        })();
                        """,
                        safe_bug,
                        safe_desc,
                )
    except Exception:
        pass


def three_frame_paths(uid: str) -> Tuple[str, str, str]:
    t0_clean = os.path.join(IMG_INTERACTION_DIR, f"{uid}_start.png")
    t0_action = os.path.join(IMG_INTERACTION_DIR, f"{uid}_action.png")
    t1_end = os.path.join(IMG_INTERACTION_DIR, f"{uid}_end.png")
    return t0_clean, t0_action, t1_end
