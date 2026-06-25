import httpx
import asyncio
import os
import json
from PIL import Image

SERVER_URL = "http://127.0.0.1:8000"

async def test_flow():
    # 1. Create a dummy image to upload
    os.makedirs("test_temp", exist_ok=True)
    image_path = "test_temp/dummy_screenshot.png"
    img = Image.new('RGB', (100, 100), color = 'blue')
    img.save(image_path)
    print(f"[Test] Created dummy image: {image_path}")

    # 2. Upload the image to the FastAPI server
    print("[Test] Uploading image to server...")
    async with httpx.AsyncClient() as client:
        with open(image_path, "rb") as f:
            response = await client.post(
                f"{SERVER_URL}/upload", 
                files={"file": ("dummy_screenshot.png", f, "image/png")}
            )
        
        assert response.status_code == 200, f"Upload failed: {response.text}"
        data = response.json()
        capture_id = data.get("capture_id")
        filename = data.get("filename")
        print(f"[Test] Image uploaded successfully. Capture ID: {capture_id}, Filename: {filename}")

        # 3. Request SSE stream
        print(f"[Test] Requesting SSE stream for capture {capture_id}...")
        
        # Verify active_agent is set to 'qwen' but it falls back to mock
        # We can read line-by-line from the stream
        async with client.stream("GET", f"{SERVER_URL}/stream/{capture_id}") as r:
            assert r.status_code == 200, f"Stream failed: {r.status_code}"
            
            async for line in r.aiter_lines():
                if line.startswith("data:"):
                    # Strip 'data: ' and parse JSON
                    event_data = line[5:].strip()
                    try:
                        parsed = json.loads(event_data)
                        text = parsed.get("text", "")
                        done = parsed.get("done", False)
                        agent = parsed.get("agent", "")
                        if text:
                            print(text, end="", flush=True)
                        if done:
                            print(f"\n[Test] Stream completed. Agent: {agent}")
                            break
                    except Exception as ex:
                        print(f"\n[Test] Parse error: {ex} on line {line}")

        # 4. Fetch all captures to verify database integration
        print("[Test] Fetching history from /captures...")
        history_resp = await client.get(f"{SERVER_URL}/captures")
        assert history_resp.status_code == 200
        history_data = history_resp.json()
        print(f"[Test] Found {len(history_data)} items in history.")
        assert any(item["id"] == capture_id for item in history_data), "Uploaded capture not found in history"

        # 5. Clean up by deleting the test capture
        print(f"[Test] Deleting capture {capture_id}...")
        del_resp = await client.delete(f"{SERVER_URL}/captures/{capture_id}")
        assert del_resp.status_code == 200
        print("[Test] Cleanup complete!")

    # Remove temporary dummy image
    try:
        os.remove(image_path)
        os.rmdir("test_temp")
    except Exception:
        pass

if __name__ == "__main__":
    asyncio.run(test_flow())
