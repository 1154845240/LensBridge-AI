import threading
import time


_lock = threading.RLock()
_hotkey_subscribers = []
_shutdown_callback = None
_started_at = time.time()
_capture_service_running = False
_capture_mode = "single"
_capture_stage = "ready"
_operation_message = "单图模式：长按鼠标左键 3 秒标记截图起点"
_queue_size = 0
_stage_deadline = None
_last_event_at = time.time()


def subscribe_hotkeys(callback):
    with _lock:
        if callback not in _hotkey_subscribers:
            _hotkey_subscribers.append(callback)


def unsubscribe_hotkeys(callback):
    with _lock:
        if callback in _hotkey_subscribers:
            _hotkey_subscribers.remove(callback)


def publish_hotkeys(hotkeys):
    with _lock:
        callbacks = list(_hotkey_subscribers)
    for callback in callbacks:
        callback(dict(hotkeys))


def set_shutdown_callback(callback):
    global _shutdown_callback
    with _lock:
        _shutdown_callback = callback


def request_shutdown():
    with _lock:
        callback = _shutdown_callback
    if callback is None:
        return False
    threading.Thread(target=callback, name="LensBridgeShutdown", daemon=True).start()
    return True


def set_capture_service_running(running):
    global _capture_service_running, _last_event_at
    with _lock:
        _capture_service_running = bool(running)
        _last_event_at = time.time()


def update_capture_status(
    *,
    mode=None,
    stage=None,
    message=None,
    queue_size=None,
    deadline=None,
):
    global _capture_mode, _capture_stage, _operation_message
    global _queue_size, _stage_deadline, _last_event_at
    with _lock:
        if mode is not None:
            _capture_mode = mode
        if stage is not None:
            _capture_stage = stage
        if message is not None:
            _operation_message = message
        if queue_size is not None:
            _queue_size = max(0, int(queue_size))
        if deadline is not None or stage != "awaiting_second_point":
            _stage_deadline = deadline
        _last_event_at = time.time()


def get_status():
    with _lock:
        return {
            "status": "running",
            "capture_service": _capture_service_running,
            "uptime_seconds": int(time.time() - _started_at),
            "capture_mode": _capture_mode,
            "capture_stage": _capture_stage,
            "operation_message": _operation_message,
            "queue_size": _queue_size,
            "stage_deadline": _stage_deadline,
            "last_event_at": _last_event_at,
        }
