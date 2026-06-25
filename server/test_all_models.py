import httpx
import asyncio
import json
import os

async def get_models(api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            models = []
            for m in data.get("models", []):
                # Filter models that support generateContent
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    # We just need the name without "models/" prefix for the openai endpoint
                    name = m["name"].replace("models/", "")
                    models.append(name)
            return models
        else:
            print("Failed to list models:", resp.status_code, resp.text)
            return []

async def test_model(api_key, model_name):
    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "请回答1+1等于多少？只需要回答数字。"}],
        "stream": False
    }
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return f"成功 (200) - 回答: {content.strip()}"
            else:
                try:
                    error_msg = resp.json().get("error", {}).get("message", resp.text)
                except:
                    error_msg = resp.text
                return f"失败 ({resp.status_code}) - {error_msg}"
    except Exception as e:
        return f"异常 - {str(e)}"

async def main():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("请先设置环境变量 GEMINI_API_KEY")
    print("获取模型列表中...")
    models = await get_models(api_key)
    
    if not models:
        print("未获取到任何支持 generateContent 的模型。")
        return
        
    print(f"共发现 {len(models)} 个支持生成的模型:\n{models}\n")
    print("-" * 50)
    
    for model in models:
        print(f"正在测试模型: {model} ... ", end="")
        result = await test_model(api_key, model)
        print(result)

if __name__ == "__main__":
    asyncio.run(main())
