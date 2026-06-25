import ctypes
import logging
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

import uvicorn

import app_paths
import runtime_state
from client import client
from server.app import app


class LoggerWriter:
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level

    def write(self, message):
        message = message.rstrip()
        if message:
            self.logger.log(self.level, message)

    def flush(self):
        return None


def configure_logging():
    app_paths.ensure_runtime_layout()
    log_path = app_paths.LOG_DIR / "lensbridge.log"
    handler = RotatingFileHandler(
        log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(message)s")
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    sys.stdout = LoggerWriter(logging.getLogger("stdout"), logging.INFO)
    sys.stderr = LoggerWriter(logging.getLogger("stderr"), logging.ERROR)


class SingleInstance:
    ERROR_ALREADY_EXISTS = 183

    def __init__(self, name="Local\\LensBridgeAI.SingleInstance"):
        self.handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
        self.already_running = ctypes.windll.kernel32.GetLastError() == self.ERROR_ALREADY_EXISTS

    def close(self):
        if self.handle:
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None


class LensBridgeApplication:
    def __init__(self):
        self.stop_event = threading.Event()
        self.server = None
        self.instance = SingleInstance()

    def shutdown(self):
        if self.stop_event.is_set():
            return
        logging.info("Shutdown requested.")
        self.stop_event.set()
        client.stop_service()
        if self.server is not None:
            self.server.should_exit = True

    def run(self):
        if self.instance.already_running:
            return 0

        app_paths.ensure_runtime_layout()
        runtime_state.set_shutdown_callback(self.shutdown)
        client.start_service()

        config = client.load_config()
        server_config = config.get("server", {})
        host = server_config.get("host", "0.0.0.0")
        port = int(server_config.get("port", 8000))
        uvicorn_config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_config=None,
            access_log=False,
        )
        self.server = uvicorn.Server(uvicorn_config)
        logging.info("LensBridge AI starting on %s:%s", host, port)

        try:
            self.server.run()
        finally:
            self.shutdown()
            deadline = time.time() + 3
            while client.is_service_running() and time.time() < deadline:
                time.sleep(0.05)
            self.instance.close()
        return 0


def main():
    configure_logging()
    application = LensBridgeApplication()
    try:
        return application.run()
    except Exception:
        logging.exception("Fatal LensBridge AI startup error.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
