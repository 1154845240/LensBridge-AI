import os
import sys
import time
import json
import asyncio
import sqlite3
import logging
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from typing import List
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import app_paths
import runtime_state

try:
    from . import database, agent_manager, file_cleanup
except ImportError:
    import database
    import agent_manager
    import file_cleanup

app = FastAPI(title="LensBridge AI Server")
app_paths.ensure_runtime_layout()

# Enable CORS for mobile browsers in the same local network
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Upload directory setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = str(app_paths.UPLOAD_DIR)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount uploaded images static folder
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.on_event("startup")
def startup_event():
    database.init_db()
    _, deleted, errors = file_cleanup.cleanup_orphan_uploads(
        UPLOAD_DIR,
        database.get_all_image_filenames(),
    )
    if deleted:
        logging.info("Removed %s orphan upload file(s).", deleted)
    if errors:
        logging.warning("Failed to remove orphan upload files: %s", errors)

# Global memory active conversation ID
active_conversation_id = None
capture_tasks = {}


def remove_capture_task(capture_id, task):
    if capture_tasks.get(capture_id) is task:
        capture_tasks.pop(capture_id, None)

def get_active_conv_id():
    global active_conversation_id
    if active_conversation_id is None:
        convs = database.get_conversations()
        if convs:
            active_conversation_id = convs[0]["id"]
        else:
            active_conversation_id = database.add_conversation("默认对话")
    return active_conversation_id


def get_agent_display_name(agent_name, config=None):
    if agent_name == "mock":
        return "Mock 演示模式"
    config = config or agent_manager.load_config()
    return (
        config.get("agents", {})
        .get(agent_name, {})
        .get("display_name")
        or agent_name
    )


def enrich_capture(capture, config=None):
    item = dict(capture)
    item["agent_display_name"] = get_agent_display_name(item.get("agent_name"), config)
    return item

@app.post("/upload")
async def upload_image(files: List[UploadFile] = File(...)):
    filenames = []
    for file in files:
        filename = f"screenshot_{int(time.time()*1000)}_{file.filename}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as buffer:
            buffer.write(await file.read())
        filenames.append(filename)
        
    config = agent_manager.load_config()
    active_agent = config.get("active_agent", "qwen")
    
    # Store in database as JSON array string
    filenames_json = json.dumps(filenames)
    
    # Associate with active conversation
    conv_id = get_active_conv_id()
    
    capture_id = database.add_capture(conv_id, filenames_json, active_agent)
    print(f"[Server] Screenshot(s) received and saved: {filenames_json} (ID: {capture_id}) in conversation: {conv_id}")
    
    return {"status": "success", "capture_id": capture_id, "filenames": filenames, "conversation_id": conv_id}

@app.get("/")
def read_root():
    return RedirectResponse(url="/view")

@app.get("/view", response_class=HTMLResponse)
def get_view():
    template_path = str(app_paths.resource_path("server", "templates", "index.html"))
    if os.path.exists(template_path):
        return FileResponse(template_path)
    return HTMLResponse("<h2>Frontend template index.html not found!</h2>")

# Conversation Management APIs
@app.get("/conversations")
def get_conversations():
    return database.get_conversations()

@app.post("/conversations")
def create_conversation(title: str = Form(None)):
    if not title:
        title = f"新对话 {time.strftime('%m-%d %H:%M')}"
    conv_id = database.add_conversation(title)
    global active_conversation_id
    active_conversation_id = conv_id  # Automatically switch to the newly created conversation
    return {"status": "success", "conversation_id": conv_id, "title": title}

@app.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int):
    filenames = database.delete_conversation(conv_id)
    deleted, errors = file_cleanup.delete_upload_files(UPLOAD_DIR, filenames)
    if errors:
        logging.warning("Conversation %s upload cleanup failed: %s", conv_id, errors)
                
    # Reset active conversation ID if the current active one was deleted
    global active_conversation_id
    if active_conversation_id == conv_id:
        active_conversation_id = None  # Will automatically select latest on next upload/view
        
    return {"status": "success", "deleted_files": deleted, "cleanup_errors": errors}

@app.get("/conversations/active")
def get_active_conversation():
    global active_conversation_id
    conv_id = get_active_conv_id()
    convs = database.get_conversations()
    active_conv = next((c for c in convs if c["id"] == conv_id), None)
    if not active_conv and convs:
        active_conv = convs[0]
        active_conversation_id = active_conv["id"]
    return {"conversation_id": active_conversation_id, "conversation": active_conv}

@app.post("/conversations/active")
def set_active_conversation(conversation_id: int = Form(...)):
    global active_conversation_id
    active_conversation_id = conversation_id
    return {"status": "success", "active_conversation_id": active_conversation_id}

@app.put("/conversations/{conv_id}")
def rename_conversation(conv_id: int, title: str = Form(...)):
    database.update_conversation_title(conv_id, title)
    return {"status": "success"}

@app.get("/conversations/{conv_id}/captures")
def get_conversation_captures(conv_id: int):
    config = agent_manager.load_config()
    return [
        enrich_capture(capture, config)
        for capture in database.get_captures_by_conversation(conv_id)
    ]

@app.get("/captures")
def get_captures():
    # Return captures of the current active conversation
    conv_id = get_active_conv_id()
    config = agent_manager.load_config()
    return [
        enrich_capture(capture, config)
        for capture in database.get_captures_by_conversation(conv_id)
    ]

@app.delete("/captures/{capture_id}")
def delete_capture(capture_id: int):
    filename_str = database.delete_capture(capture_id)
    if filename_str:
        deleted, errors = file_cleanup.delete_upload_files(UPLOAD_DIR, [filename_str])
        if errors:
            logging.warning("Capture %s upload cleanup failed: %s", capture_id, errors)
        return {"status": "success", "deleted_files": deleted, "cleanup_errors": errors}
    return {"status": "error", "message": "Capture not found"}

@app.post("/captures/text")
def post_text_capture(text: str = Form(...)):
    conv_id = get_active_conv_id()
    config = agent_manager.load_config()
    agent_name = config.get("active_agent", "mock")
    
    # Store text capture with empty image filename
    capture_id = database.add_capture(conv_id, "", agent_name, user_prompt=text)
    return {"status": "success", "capture_id": capture_id}

@app.post("/captures/{capture_id}/retry")
async def retry_capture(capture_id: int):
    cap = database.get_capture(capture_id)
    if cap:
        config = agent_manager.load_config()
        active_agent = config.get("active_agent", "mock")
        task = capture_tasks.pop(capture_id, None)
        if task and not task.done():
            task.cancel()
        database.reset_capture_analysis(capture_id, active_agent)
        return {"status": "success", "agent_name": active_agent}
    return {"status": "error", "message": "Capture not found"}

@app.post("/captures/latest/retry")
async def retry_latest_capture():
    conv_id = get_active_conv_id()
    captures = database.get_captures_by_conversation(conv_id)
    if captures:
        latest = captures[-1]
        config = agent_manager.load_config()
        active_agent = config.get("active_agent", "mock")
        task = capture_tasks.pop(latest["id"], None)
        if task and not task.done():
            task.cancel()
        database.reset_capture_analysis(latest["id"], active_agent)
        return {"status": "success", "capture_id": latest["id"], "agent_name": active_agent}
    return {"status": "error", "message": "No captures found in active conversation"}

@app.post("/captures/clear")
def clear_captures():
    filenames = database.clear_all_history()
    deleted, errors = file_cleanup.delete_upload_files(UPLOAD_DIR, filenames)
    if errors:
        logging.warning("History upload cleanup failed: %s", errors)
    global active_conversation_id
    active_conversation_id = None
    return {"status": "success", "deleted_files": deleted, "cleanup_errors": errors}


def capture_filepaths(cap):
    filename_str = cap["image_filename"]
    try:
        filenames = json.loads(filename_str) if filename_str.startswith("[") else [filename_str]
    except Exception:
        filenames = [filename_str]
    return [os.path.join(UPLOAD_DIR, filename) for filename in filenames if filename]


async def generate_capture_response(capture_id):
    cap = database.get_capture(capture_id)
    if not cap:
        return

    accumulated_text = ""
    database.update_ai_response(capture_id, "", "processing")
    try:
        async for chunk in agent_manager.call_agent_stream(
            capture_filepaths(cap),
            user_prompt=cap.get("user_prompt", ""),
            agent_name=cap["agent_name"],
        ):
            accumulated_text += chunk
            database.update_ai_response(capture_id, accumulated_text, "processing")
        database.update_ai_response(capture_id, accumulated_text, "completed")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        error_msg = f"\n\n[流处理异常: {str(exc)}]"
        database.update_ai_response(capture_id, accumulated_text + error_msg, "failed")


@app.get("/stream/{capture_id}")
async def stream_capture(capture_id: int):
    cap = database.get_capture(capture_id)
    if not cap:
        async def error_generator():
            yield f"data: {json.dumps({'error': '未找到截图记录', 'done': True})}\n\n"
        return StreamingResponse(error_generator(), media_type="text/event-stream")

    task = capture_tasks.get(capture_id)
    if cap["status"] in {"pending", "processing"}:
        if task is None or task.done():
            task = asyncio.create_task(generate_capture_response(capture_id))
            capture_tasks[capture_id] = task
            task.add_done_callback(lambda completed: remove_capture_task(capture_id, completed))

    async def sse_generator():
        sent_length = 0
        while True:
            current = database.get_capture(capture_id)
            if not current:
                yield f"data: {json.dumps({'error': '记录已删除', 'done': True})}\n\n"
                return

            response_text = current["ai_response"] or ""
            if len(response_text) > sent_length:
                delta = response_text[sent_length:]
                sent_length = len(response_text)
                yield f"data: {json.dumps({'text': delta, 'done': False, 'agent': current['agent_name']})}\n\n"

            if current["status"] in {"completed", "failed"}:
                yield f"data: {json.dumps({'text': '', 'done': True, 'agent': current['agent_name']})}\n\n"
                return
            await asyncio.sleep(0.1)

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

# Agent config & settings APIs
@app.get("/config/agent")
def get_config_agent():
    try:
        config = agent_manager.load_config()
        active = config.get("active_agent", "qwen")
        agents_list = list(config.get("agents", {}).keys())
        if "mock" not in agents_list:
            agents_list.append("mock")
            
        masked_agents = {}
        for name, info in config.get("agents", {}).items():
            key = info.get("api_key", "")
            masked_key = key
            if key and not key.startswith("YOUR_") and len(key) > 6:
                masked_key = key[:3] + "..." + key[-3:]
            masked_agents[name] = {
                "display_name": info.get("display_name", name),
                "model": info.get("model", ""),
                "api_url": info.get("api_url", ""),
                "api_key": masked_key,
                "system_prompt": info.get("system_prompt", "")
            }
            
        return {
            "active_agent": config.get("active_agent", "qwen"),
            "global_system_prompt": config.get("global_system_prompt", ""),
            "hotkeys": config.get("hotkeys", {
                "toggle": "f8",
                "send": "f9",
                "clear": "esc",
                "retry": "f10",
                "open": "f12"
            }),
            "available_agents": agents_list,
            "agents": masked_agents
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/config/agent")
def set_config_agent(active_agent: str = Form(...)):
    try:
        config = agent_manager.load_config()
        if active_agent != "mock" and active_agent not in config.get("agents", {}):
            raise ValueError(f"模型配置不存在: {active_agent}")
        config["active_agent"] = active_agent
        agent_manager.save_config(config)
        return {
            "status": "success",
            "active_agent": active_agent,
            "display_name": get_agent_display_name(active_agent, config),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/config/agent/{agent_name}")
def delete_agent(agent_name: str):
    try:
        config = agent_manager.load_config()
        if "agents" in config and agent_name in config["agents"]:
            del config["agents"][agent_name]
            
            # Switch active agent if the deleted one was active
            if config.get("active_agent") == agent_name:
                available = list(config["agents"].keys())
                config["active_agent"] = available[0] if available else "mock"
                
            agent_manager.save_config(config)
            return {"status": "success"}
        return {"status": "error", "message": "Agent not found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/config/settings")
def update_agent_settings(
    agent_name: str = Form(...),
    api_key: str = Form(...),
    model: str = Form(...),
    api_url: str = Form(...),
    display_name: str = Form(...),
    system_prompt: str = Form("")
):
    try:
        config = agent_manager.load_config()
        if "agents" not in config:
            config["agents"] = {}
            
        existing_key = config["agents"].get(agent_name, {}).get("api_key", "")
        masked_existing = existing_key[:3] + "..." + existing_key[-3:] if (existing_key and len(existing_key) > 6) else ""
        
        if api_key == masked_existing and existing_key:
            final_key = existing_key
        elif api_key.endswith("...") and existing_key:
            final_key = existing_key
        else:
            final_key = api_key
            
        config["agents"][agent_name] = {
            "display_name": display_name,
            "api_key": final_key,
            "model": model,
            "api_url": api_url,
            "system_prompt": system_prompt
        }
        agent_manager.save_config(config)
        return {"status": "success", "agent_name": agent_name}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/config/global_prompt")
def update_global_prompt(system_prompt: str = Form("")):
    try:
        config = agent_manager.load_config()
        config["global_system_prompt"] = system_prompt
        agent_manager.save_config(config)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

class HotkeysConfig(BaseModel):
    toggle: str
    send: str
    clear: str
    retry: str
    open: str = "f12"


def normalize_hotkey(value):
    aliases = {
        "control": "ctrl",
        "option": "alt",
        "win": "cmd",
        "windows": "cmd",
        "meta": "cmd",
        "escape": "esc",
        "return": "enter",
    }
    modifiers = {"ctrl", "alt", "shift", "cmd"}
    named_keys = {"esc", "enter", "space", "tab", "backspace", "delete", "home", "end"}
    parts = [aliases.get(part.strip().lower(), part.strip().lower()) for part in value.split("+")]
    if not parts or any(not part for part in parts):
        raise ValueError(f"快捷键格式不正确: {value}")
    if len(parts) != len(set(parts)):
        raise ValueError(f"快捷键包含重复按键: {value}")

    regular_keys = []
    for part in parts:
        is_function_key = part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 12
        if part in modifiers:
            continue
        if len(part) == 1 and part.isalnum():
            regular_keys.append(part)
            continue
        if part in named_keys or is_function_key:
            regular_keys.append(part)
            continue
        raise ValueError(f"不支持的快捷键按键: {part}")

    if len(regular_keys) != 1:
        raise ValueError("组合快捷键必须包含且只能包含一个普通按键")

    ordered = [modifier for modifier in ("ctrl", "alt", "shift", "cmd") if modifier in parts]
    ordered.append(regular_keys[0])
    return "+".join(ordered)


@app.post("/config/hotkeys")
def update_hotkeys(req: HotkeysConfig):
    try:
        hotkeys = {
            "toggle": normalize_hotkey(req.toggle),
            "send": normalize_hotkey(req.send),
            "clear": normalize_hotkey(req.clear),
            "retry": normalize_hotkey(req.retry),
            "open": normalize_hotkey(req.open),
        }
        if len(set(hotkeys.values())) != len(hotkeys):
            raise ValueError("快捷键不能重复")
        hotkey_sets = {name: set(value.split("+")) for name, value in hotkeys.items()}
        names = list(hotkey_sets)
        for index, first_name in enumerate(names):
            for second_name in names[index + 1:]:
                first = hotkey_sets[first_name]
                second = hotkey_sets[second_name]
                if first.issubset(second) or second.issubset(first):
                    raise ValueError("快捷键不能互相包含，例如 Q 与 Alt+Q 不能同时使用")
        config = agent_manager.load_config()
        config["hotkeys"] = hotkeys
        agent_manager.save_config(config)
        runtime_state.publish_hotkeys(hotkeys)
        return {"status": "success", "hotkeys": hotkeys, "applied": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/system/status")
def get_system_status(request: Request):
    status = runtime_state.get_status()
    status["can_shutdown"] = request.client.host in {"127.0.0.1", "::1"}
    return status


@app.post("/system/shutdown")
def shutdown_system(request: Request):
    if request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="仅允许在运行 LensBridge AI 的电脑上退出程序")
    if not runtime_state.request_shutdown():
        raise HTTPException(status_code=503, detail="当前运行方式不支持网页退出")
    return {"status": "shutting_down"}


if __name__ == "__main__":
    import uvicorn
    # Load host/port from config
    try:
        config = agent_manager.load_config()
        host = config["server"].get("host", "0.0.0.0")
        port = config["server"].get("port", 8000)
    except Exception:
        host = "0.0.0.0"
        port = 8000
        
    print(f"[Server] Starting FastAPI server on {host}:{port}...")
    uvicorn.run(app, host=host, port=port)
