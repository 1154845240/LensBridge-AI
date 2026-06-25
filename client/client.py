import os
import sys
import time
import ctypes
import threading
import requests
import json
import webbrowser
from pynput import mouse, keyboard
from PIL import ImageGrab

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import app_paths
import runtime_state

app_paths.ensure_runtime_layout()

# DPI Awareness for high resolution monitors
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    print("[Client] DPI awareness set successfully.")
except Exception as e:
    print(f"[Client] DPI awareness warning: {e}")

# Global states
coord_a = None
coord_b = None
timer_a = None
state_lock = threading.Lock()

is_batch_mode = False
image_queue = []
hotkey_lock = threading.RLock()
service_lock = threading.RLock()
service_stop_event = threading.Event()
pressed_keys = set()
active_hotkey_actions = set()
service_thread = None
mouse_listener = None
keyboard_listener = None


def current_mode_name():
    return "batch" if is_batch_mode else "single"


def ready_message():
    if is_batch_mode:
        return f"多图模式：长按左键 3 秒开始选区；当前队列 {len(image_queue)} 张"
    return "单图模式：长按鼠标左键 3 秒标记截图起点"


def publish_capture_status(stage="ready", message=None, deadline=None):
    runtime_state.update_capture_status(
        mode=current_mode_name(),
        stage=stage,
        message=message or ready_message(),
        queue_size=len(image_queue),
        deadline=deadline,
    )

# Server address configuration (will try to load from config.json)
SERVER_URL = "http://127.0.0.1:8000"
HOTKEYS_CONFIG = {
    "toggle": "f8",
    "send": "f9",
    "clear": "esc",
    "retry": "f10",
    "open": "f12"
}

config_path = str(app_paths.CONFIG_PATH)


def load_config():
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            return json.load(config_file)
    except Exception as exc:
        print(f"[Client] Error loading config: {exc}")
        return {}


srv_config = load_config()
port = srv_config.get("server", {}).get("port", 8000)
SERVER_URL = f"http://127.0.0.1:{port}"
HOTKEYS_CONFIG = srv_config.get("hotkeys", HOTKEYS_CONFIG)

KEY_ALIASES = {
    "control": "ctrl",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
    "shift_l": "shift",
    "shift_r": "shift",
    "cmd_l": "cmd",
    "cmd_r": "cmd",
    "win": "cmd",
    "windows": "cmd",
    "meta": "cmd",
    "escape": "esc",
    "return": "enter",
}


def normalize_key_name(name):
    return KEY_ALIASES.get(name, name)


def parse_hotkey(k_str, default_key):
    try:
        parts = {
            normalize_key_name(part.strip().lower())
            for part in k_str.split("+")
            if part.strip()
        }
        if not parts:
            raise ValueError("empty hotkey")
        return frozenset(parts)
    except Exception:
        return default_key

KEY_TOGGLE = parse_hotkey(HOTKEYS_CONFIG.get("toggle", "f8"), frozenset({"f8"}))
KEY_SEND = parse_hotkey(HOTKEYS_CONFIG.get("send", "f9"), frozenset({"f9"}))
KEY_CLEAR = parse_hotkey(HOTKEYS_CONFIG.get("clear", "esc"), frozenset({"esc"}))
KEY_RETRY = parse_hotkey(HOTKEYS_CONFIG.get("retry", "f10"), None) # Optional, can be None
KEY_OPEN = parse_hotkey(HOTKEYS_CONFIG.get("open", "f12"), frozenset({"f12"}))


def update_hotkeys(hotkeys):
    global HOTKEYS_CONFIG, KEY_TOGGLE, KEY_SEND, KEY_CLEAR, KEY_RETRY, KEY_OPEN
    with hotkey_lock:
        HOTKEYS_CONFIG = dict(hotkeys)
        KEY_TOGGLE = parse_hotkey(HOTKEYS_CONFIG.get("toggle", "f8"), frozenset({"f8"}))
        KEY_SEND = parse_hotkey(HOTKEYS_CONFIG.get("send", "f9"), frozenset({"f9"}))
        KEY_CLEAR = parse_hotkey(HOTKEYS_CONFIG.get("clear", "esc"), frozenset({"esc"}))
        KEY_RETRY = parse_hotkey(HOTKEYS_CONFIG.get("retry", "f10"), None)
        KEY_OPEN = parse_hotkey(HOTKEYS_CONFIG.get("open", "f12"), frozenset({"f12"}))
        pressed_keys.clear()
        active_hotkey_actions.clear()
    print(f"[Client] Hotkeys applied immediately: {HOTKEYS_CONFIG}")


runtime_state.subscribe_hotkeys(update_hotkeys)

# Temporary variables for tracking mouse click duration
click_press_time = None
click_press_pos = None


def on_click(x, y, button, pressed):
    global click_press_time, click_press_pos
    
    if button == mouse.Button.left:
        if pressed:
            click_press_time = time.time()
            click_press_pos = (x, y)
        else:
            if click_press_time is not None:
                duration = time.time() - click_press_time
                # Detect long press of 3 seconds or more
                if duration >= 3.0:
                    release_pos = (x, y)
                    print(f"\n[Client] Left-button long press detected! Duration: {duration:.2f}s at {release_pos}")
                    handle_long_press(release_pos)
                
                # Reset tracking
                click_press_time = None
                click_press_pos = None

def handle_long_press(pos):
    global coord_a, coord_b, timer_a
    with state_lock:
        if coord_a is None:
            coord_a = pos
            print(f"[Client] Coordinate A captured: {coord_a}")
            print("[Client] You have 15 seconds to long-press again to capture Coordinate B.")
            
            # Start 15s timer
            if timer_a is not None:
                timer_a.cancel()
            timer_a = threading.Timer(15.0, reset_coord_a_timeout)
            timer_a.start()
            publish_capture_status(
                stage="awaiting_second_point",
                message="已标记起点 A，请在 15 秒内再次长按左键 3 秒标记终点 B",
                deadline=time.time() + 15,
            )
        else:
            # Cancel timeout timer
            if timer_a is not None:
                timer_a.cancel()
                timer_a = None
            
            coord_b = pos
            print(f"[Client] Coordinate B captured: {coord_b}")
            publish_capture_status(
                stage="capturing",
                message="已标记终点 B，正在截取并处理选定区域…",
            )
            
            # Perform screenshot
            capture_and_save(coord_a, coord_b)
            
            # Reset states
            coord_a = None
            coord_b = None

def reset_coord_a_timeout():
    global coord_a, timer_a
    with state_lock:
        if coord_a is not None:
            print(f"\n[Client] Time limit exceeded (15 seconds). Resetting Coordinate A ({coord_a}).")
            coord_a = None
            timer_a = None
            publish_capture_status(
                stage="timeout",
                message="选区操作已超时，请重新长按左键 3 秒标记起点",
            )

def capture_and_save(a, b):
    x1, y1 = a
    x2, y2 = b
    
    # Calculate bounding box
    bbox = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    
    if width < 10 or height < 10:
        print(f"[Client] Area too small ({width}x{height}). Capture ignored.")
        publish_capture_status(
            stage="error",
            message="选区过小，已忽略；请重新选择更大的截图区域",
        )
        return
        
    print(f"[Client] Capturing area: {bbox} (width: {width}, height: {height})...")
    try:
        # Silent screenshot grab
        img = ImageGrab.grab(bbox=bbox)
        
        # Save to local folder temporarily
        output_dir = str(app_paths.TEMP_DIR)
        os.makedirs(output_dir, exist_ok=True)
        filename = f"capture_{int(time.time())}.png"
        filepath = os.path.join(output_dir, filename)
        img.save(filepath)
        print(f"[Client] Saved locally to {filepath}. Uploading...")
        
        if not is_batch_mode:
            # Upload immediately
            publish_capture_status(stage="uploading", message="截图完成，正在上传并发起 AI 分析…")
            upload_batch_to_server([filepath])
        else:
            image_queue.append(filepath)
            print(f"[Client] Added to batch queue (Total: {len(image_queue)}). Press F9 to send, Esc to clear.")
            publish_capture_status(
                stage="queued",
                message=f"截图已加入多图队列，当前共 {len(image_queue)} 张；按发送快捷键开始分析",
            )
            
    except Exception as e:
        print(f"[Client] Error during screen capture: {e}")
        publish_capture_status(stage="error", message=f"截图失败：{e}")

def upload_batch_to_server(filepaths):
    if not filepaths:
        print("[Client] No files to upload.")
        publish_capture_status(stage="ready")
        return
        
    try:
        url = f"{SERVER_URL}/upload"
        
        files_data = []
        opened_files = []
        
        for fp in filepaths:
            f = open(fp, 'rb')
            opened_files.append(f)
            files_data.append(('files', (os.path.basename(fp), f, 'image/png')))
            
        try:
            response = requests.post(url, files=files_data, timeout=20)
            if response.status_code == 200:
                data = response.json()
                print(f"[Client] {len(filepaths)} screenshot(s) uploaded successfully! Capture ID: {data.get('capture_id')}")
                
                # Delete temporary files
                for fp in filepaths:
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
                print(f"[Client] Temporary local screenshot file(s) deleted.")
                publish_capture_status(
                    stage="uploaded",
                    message=f"{len(filepaths)} 张截图已发送，AI 正在分析",
                )
            else:
                print(f"[Client] Server returned error {response.status_code}: {response.text}")
                publish_capture_status(
                    stage="error",
                    message=f"上传失败：服务器返回 {response.status_code}",
                )
        finally:
            for f in opened_files:
                f.close()
                
    except Exception as e:
        print(f"[Client] Failed to upload screenshot to server: {e}")
        publish_capture_status(stage="error", message=f"上传失败：{e}")

def trigger_retry_on_server():
    try:
        url = f"{SERVER_URL}/captures/latest/retry"
        response = requests.post(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                print(f"\n[Client] Successfully triggered retry for capture {data.get('capture_id')}")
            else:
                print(f"\n[Client] Could not trigger retry: {data.get('message')}")
        else:
            print(f"\n[Client] Server returned error {response.status_code} for retry.")
    except Exception as e:
        print(f"\n[Client] Failed to trigger retry on server: {e}")

def key_to_token(key):
    if isinstance(key, keyboard.KeyCode):
        if key.char:
            return key.char.lower()
        return None
    name = getattr(key, "name", None)
    return normalize_key_name(name.lower()) if name else None


def on_press(key):
    global is_batch_mode, image_queue
    token = key_to_token(key)
    if token:
        pressed_keys.add(token)

    with hotkey_lock:
        bindings = {
            "toggle": KEY_TOGGLE,
            "send": KEY_SEND,
            "clear": KEY_CLEAR,
            "retry": KEY_RETRY,
            "open": KEY_OPEN,
        }

    triggered_action = next(
        (
            action
            for action, hotkey in bindings.items()
            if hotkey
            and hotkey.issubset(pressed_keys)
            and action not in active_hotkey_actions
        ),
        None,
    )
    if triggered_action:
        active_hotkey_actions.add(triggered_action)
    
    try:
        if triggered_action == "toggle":
            is_batch_mode = not is_batch_mode
            status = "BATCH MODE (Multi-Image)" if is_batch_mode else "SINGLE MODE (Auto-send)"
            print(f"\n[Client] ===================================")
            print(f"[Client] Mode toggled: {status}")
            print(f"[Client] ===================================")
            publish_capture_status(
                stage="mode_changed",
                message=(
                    f"已切换为多图模式；当前队列 {len(image_queue)} 张"
                    if is_batch_mode
                    else "已切换为单图模式；截图完成后将自动发送"
                ),
            )
            
        elif triggered_action == "send":
            if is_batch_mode:
                if len(image_queue) > 0:
                    print(f"\n[Client] Send pressed. Sending {len(image_queue)} images in batch...")
                    files_to_send = list(image_queue)
                    image_queue.clear()
                    publish_capture_status(
                        stage="uploading",
                        message=f"正在发送 {len(files_to_send)} 张队列截图…",
                    )
                    threading.Thread(target=upload_batch_to_server, args=(files_to_send,)).start()
                else:
                    print(f"\n[Client] Batch queue is empty. Nothing to send.")
                    publish_capture_status(stage="ready", message="多图队列为空，请先截取图片")
                    
        elif triggered_action == "clear":
            if is_batch_mode and len(image_queue) > 0:
                print(f"\n[Client] Clear pressed. Clearing batch queue ({len(image_queue)} images deleted).")
                for fp in image_queue:
                    try:
                        os.remove(fp)
                    except:
                        pass
                image_queue.clear()
                publish_capture_status(stage="cleared", message="多图队列已清空")
                
        elif triggered_action == "retry":
            print(f"\n[Client] Retry pressed. Asking server to re-analyze the latest capture...")
            threading.Thread(target=trigger_retry_on_server).start()

        elif triggered_action == "open":
            page_url = f"{SERVER_URL}/view"
            print(f"\n[Client] Opening LensBridge AI page: {page_url}")
            threading.Thread(target=webbrowser.open, args=(page_url,), daemon=True).start()
            
    except AttributeError:
        pass


def on_release(key):
    token = key_to_token(key)
    if token:
        pressed_keys.discard(token)
    with hotkey_lock:
        bindings = {
            "toggle": KEY_TOGGLE,
            "send": KEY_SEND,
            "clear": KEY_CLEAR,
            "retry": KEY_RETRY,
            "open": KEY_OPEN,
        }
    for action, hotkey in bindings.items():
        if not hotkey or not hotkey.issubset(pressed_keys):
            active_hotkey_actions.discard(action)


def _service_loop():
    global mouse_listener, keyboard_listener, SERVER_URL
    service_stop_event.clear()
    config = load_config()
    server_port = config.get("server", {}).get("port", 8000)
    SERVER_URL = f"http://127.0.0.1:{server_port}"
    update_hotkeys(config.get("hotkeys", HOTKEYS_CONFIG))
    publish_capture_status()

    mouse_listener = mouse.Listener(on_click=on_click)
    keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    mouse_listener.start()
    keyboard_listener.start()
    runtime_state.set_capture_service_running(True)

    try:
        last_mtime = os.path.getmtime(config_path) if os.path.exists(config_path) else 0
        while (
            not service_stop_event.wait(0.5)
            and mouse_listener.is_alive()
            and keyboard_listener.is_alive()
        ):
            if os.path.exists(config_path):
                current_mtime = os.path.getmtime(config_path)
                if current_mtime > last_mtime:
                    last_mtime = current_mtime
                    updated_config = load_config()
                    update_hotkeys(updated_config.get("hotkeys", HOTKEYS_CONFIG))
    finally:
        if mouse_listener is not None:
            mouse_listener.stop()
        if keyboard_listener is not None:
            keyboard_listener.stop()
        runtime_state.set_capture_service_running(False)
        runtime_state.update_capture_status(
            stage="stopped",
            message="截图监听已停止",
            queue_size=len(image_queue),
        )


def start_service():
    global service_thread
    with service_lock:
        if service_thread is not None and service_thread.is_alive():
            return
        service_thread = threading.Thread(
            target=_service_loop,
            name="LensBridgeCaptureService",
            daemon=True,
        )
        service_thread.start()


def stop_service():
    service_stop_event.set()
    with service_lock:
        thread = service_thread
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=2)


def is_service_running():
    with service_lock:
        return service_thread is not None and service_thread.is_alive()


if __name__ == "__main__":
    print("=============================================================")
    print("LensBridge AI - Windows Silent Capture Client")
    print("=============================================================")
    print("Instruction:")
    print("  1. LONG PRESS left mouse button for 3 seconds to set Coordinate A.")
    print("  2. Within 15 seconds, LONG PRESS left mouse button for 3 seconds to set Coordinate B.")
    print("  3. The rectangle between A and B will be silently captured.")
    print("-------------------------------------------------------------")
    print("Keyboard Shortcuts:")
    print(f"  [{HOTKEYS_CONFIG.get('toggle', 'f8').upper()}]  Toggle between Single Image Mode and Multi-Image Batch Mode.")
    print(f"  [{HOTKEYS_CONFIG.get('send', 'f9').upper()}]  Send all queued images to AI (in Batch Mode).")
    print(f"  [{HOTKEYS_CONFIG.get('clear', 'esc').upper()}]  Clear image queue (in Batch Mode).")
    if HOTKEYS_CONFIG.get('retry'):
        print(f"  [{HOTKEYS_CONFIG.get('retry').upper()}]  Retry / Re-analyze the latest capture.")
    print(f"  [{HOTKEYS_CONFIG.get('open', 'f12').upper()}]  Open LensBridge AI page.")
    print("Press Ctrl+C in this terminal to exit.")
    print("=============================================================")
    
    start_service()
    try:
        while is_service_running():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[Client] Exiting...")
        stop_service()
