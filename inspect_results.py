import os
import json
import glob
import sys

def inspect_latest_injection():
    # 1. Find latest metadata
    meta_dir = os.path.join("dataset_injected", "raw_metadata")
    if not os.path.exists(meta_dir):
        print("[-] No metadata directory found.")
        return

    files = glob.glob(os.path.join(meta_dir, "int_*.json"))
    if not files:
        print("[-] No injection data found.")
        return

    latest_file = max(files, key=os.path.getmtime)
    print(f"[*] Analyzing latest injection: {os.path.basename(latest_file)}")

    with open(latest_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 2. Extract Key Info
    bug_type = data.get("bug_type", "Unknown")
    desc = data.get("description", "")
    interceptor_logs = data.get("interceptor_logs", [])
    
    print(f"\nTime: {data.get('timestamp')}")
    print(f"Bug Type: {bug_type}")
    print(f"Description: {desc}")
    
    # 3. Verification Logic
    print("\n--- Verification Report ---")
    
    # A. Log Verification
    if interceptor_logs:
        print(f"[PASSED] Network Interceptor: {len(interceptor_logs)} logs captured.")
        for log in interceptor_logs:
            print(f"  - {log.get('type')}: {log.get('url')}")
    elif bug_type in ["Timeout_Hang", "Operation_No_Response", "Unexpected_Task_Result"]:
        print(f"[WARNING] Bug type is '{bug_type}' but no network logs were captured.")
        print("  Possible reasons: Request didn't trigger, or page used navigation instead of fetch/XHR.")
    else:
        print(f"[INFO] Bug type '{bug_type}' usually relies on DOM/Input, not network.")

    # B. Image Verification
    img_root = os.path.dirname(meta_dir) # dataset_injected
    images = data.get("images", {})
    
    print("\n--- Generated Images ---")
    
    paths = {
        "Start (Clean)": images.get("start"),
        "Action (Overlay)": images.get("action"),
        "End (Overlay)": images.get("end")
    }

    for label, rel_path in paths.items():
        if rel_path:
            full_path = os.path.join(os.getcwd(), "dataset_injected", rel_path).replace("/", "\\")
            exists = os.path.exists(full_path)
            status = "Exists" if exists else "MISSING"
            print(f"{label}: {status}")
            print(f"  Path: {full_path}")
            if label == "Start (Clean)":
                print("  (Note: This image intentionally has NO overlay)")
            else:
                print("  (Note: This image SHOULD have the black/red overlay tag)")
        else:
             print(f"{label}: Not recorded")

if __name__ == "__main__":
    inspect_latest_injection()
