import json
import base64
import os
import sys
import httpx
import asyncio

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import app_paths

app_paths.ensure_runtime_layout()
CONFIG_PATH = str(app_paths.CONFIG_PATH)

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    temp_path = f"{CONFIG_PATH}.tmp"
    with open(temp_path, "w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=2, ensure_ascii=False)
        config_file.flush()
        os.fsync(config_file.fileno())
    os.replace(temp_path, CONFIG_PATH)

def get_image_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

async def call_agent_stream(image_paths, user_prompt="", agent_name=None):
    config = load_config()
    active_agent = agent_name or config.get("active_agent", "qwen")
    
    # If active_agent is set to mock, or we want a default safe fallback
    if active_agent == "mock":
        mock_response = (
            "### 🔍 LensBridge AI 屏幕分析报告 (MOCK)\n\n"
            "您刚刚截取了一张屏幕图像！以下是 AI Agent 的模拟分析解答：\n\n"
            "1. **系统状态**：已成功捕获屏幕并无感上传至后端服务器。\n"
            "2. **图片大小**：检测到图像文件已保存在服务器 uploads 目录下。\n"
            "3. **Markdown 渲染测试**：\n"
            "   - **数学公式**：$E = mc^2$\n"
            "   - **代码块测试**：\n"
            "     ```python\n"
            "     def hello_lensbridge():\n"
            "         print(\"Hello, LensBridge AI!\")\n"
            "     ```\n"
            "4. **提示**：若要使用真实大模型，请在 `server/config.json` 中配置对应的 `api_key`，并将 `active_agent` 切换为 `qwen` 或 `doubao`。"
        )
        for char in mock_response:
            yield char
            await asyncio.sleep(0.02)
        return

    agent_config = config["agents"].get(active_agent)
    if not agent_config:
        yield f"[错误: 找不到 Agent '{active_agent}' 的配置]"
        return
        
    api_key = agent_config.get("api_key")
    model = agent_config.get("model")
    api_url = agent_config.get("api_url")
    
    if not api_key or api_key.startswith("YOUR_"):
        yield f"[提示: '{active_agent}' 的 API Key 未配置，已自动切换到 Mock 演示模式。]\n\n"
        # Fallback to mock streaming
        async for chunk in call_agent_stream_mock():
            yield chunk
        return

    # Convert images to base64 and build content array
    try:
        final_prompt = user_prompt if user_prompt else "请分析屏幕截图。"
        user_content = [
            {
                "type": "text",
                "text": final_prompt
            }
        ]
        
        for ip in image_paths:
            base64_image = get_image_base64(ip)
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64_image}"
                }
            })
    except Exception as e:
        yield f"[错误: 读取图片失败: {str(e)}]"
        return
        yield f"[错误: 读取图片文件失败: {str(e)}]"
        return

    # Prepare standard OpenAI compatible payload
    headers = {
        "Authorization": f"Bearer {api_key}",
        "x-goog-api-key": api_key,
        "api-key": api_key,
        "Content-Type": "application/json"
    }
    
    system_prompt = config.get("global_system_prompt", "").strip()
    
    messages = []
    if system_prompt:
        messages.append({
            "role": "system",
            "content": system_prompt
        })
        
    messages.append({
        "role": "user",
        "content": user_content
    })

    payload = {
        "model": model,
        "messages": messages,
        "stream": True
    }

    url = f"{api_url.rstrip('/')}/chat/completions"
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    yield f"[接口调用错误 (状态码 {response.status_code}): {error_text.decode('utf-8')}]"
                    return
                
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            choice = data.get("choices", [{}])[0]
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except Exception:
                            continue
    except Exception as e:
        yield f"[网络或接口调用异常: {str(e)}]"

async def call_agent_stream_mock():
    mock_response = (
        "### 🔍 LensBridge AI 屏幕分析报告 (MOCK 模式)\n\n"
        "由于您未在 `server/config.json` 中配置有效的 API Key，系统已自动进入 **Mock 演示模式**。\n\n"
        "#### 1. 系统核心流程验证：\n"
        "- 💻 **客户端**：双长按 3 秒捕获 -> 本地静默裁剪 -> 发送至 FastAPI。\n"
        "- 🚀 **服务端**：接收图片保存 -> 存入 SQLite 数据库 -> 唤醒 SSE 消息队列。\n"
        "- 📱 **手机端**：同局域网设备加载界面 -> SSE 开启长链接监听 -> 实时打字机流式展示。\n\n"
        "#### 2. Markdown 渲染及格式测试：\n"
        "- **代码片段**：\n"
        "  ```javascript\n"
        "  // 手机端 SSE 监听实现\n"
        "  const eventSource = new EventSource(`/stream/${id}`);\n"
        "  eventSource.onmessage = (event) => {\n"
        "      console.log(event.data);\n"
        "  };\n"
        "  ```\n"
        "- **列表渲染**：此行测试了 Markdown 渲染的无序列表及加粗文字。\n\n"
        "请在 `server/config.json` 中填写正确的 API 密钥，并将 `active_agent` 设置为您的 Agent 即可体验真实 AI 分析！"
    )
    for char in mock_response:
        yield char
        await asyncio.sleep(0.01)
