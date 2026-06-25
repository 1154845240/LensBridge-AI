import httpx
import asyncio
import json
import os

async def main():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("请先设置环境变量 GEMINI_API_KEY")
    model = "gemini-2.5-flash"  # Changed to 2.5-flash
    
    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "你好，能听到我说话吗？"}],
        "stream": False
    }
    
    print("Testing with new key and gemini-2.5-flash...")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=payload)
            print("Status:", resp.status_code)
            print("Response:", resp.text)
    except Exception as e:
        print("Error:", str(e))

if __name__ == "__main__":
    asyncio.run(main())
