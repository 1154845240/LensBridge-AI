import httpx
import asyncio
import json
import os

async def main():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("请先设置环境变量 GEMINI_API_KEY")
    model = "gemini-2.5-flash"
    
    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    
    # Try using x-goog-api-key header instead of Authorization: Bearer
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hello! Are you working?"}],
        "stream": False
    }
    
    print("Testing with x-goog-api-key header...")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=payload)
        print("Status:", resp.status_code)
        print("Response:", resp.text)
        
    print("\nTesting with url?key= param...")
    url2 = f"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions?key={api_key}"
    headers2 = {
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url2, headers=headers2, json=payload)
        print("Status:", resp.status_code)
        print("Response:", resp.text)

if __name__ == "__main__":
    asyncio.run(main())
