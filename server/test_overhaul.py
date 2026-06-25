import httpx
import asyncio
import os
import json
from PIL import Image

SERVER_URL = "http://127.0.0.1:8000"

async def test_overhaul_flow():
    print("=============================================================")
    print("[Overhaul Test] Starting End-to-End Overhaul Validation")
    print("=============================================================")

    # 1. Create a dummy image
    os.makedirs("test_temp_overhaul", exist_ok=True)
    img_path = "test_temp_overhaul/test_img.png"
    img = Image.new('RGB', (200, 200), color='green')
    img.save(img_path)
    print(f"[Test] Created test image: {img_path}")

    async with httpx.AsyncClient() as client:
        # 2. Get active conversation initially (should be the default one)
        resp_act = await client.get(f"{SERVER_URL}/conversations/active")
        assert resp_act.status_code == 200
        act_data = resp_act.json()
        default_conv_id = act_data.get("conversation_id")
        print(f"[Test] Default active conversation ID: {default_conv_id}")
        assert default_conv_id is not None, "Should automatically initialize a default conversation"

        # 3. Create a new conversation: "测试对话 A"
        resp_new = await client.post(
            f"{SERVER_URL}/conversations",
            data={"title": "测试对话 A"}
        )
        assert resp_new.status_code == 200
        new_data = resp_new.json()
        conv_a_id = new_data.get("conversation_id")
        print(f"[Test] Created '测试对话 A' ID: {conv_a_id}")
        assert conv_a_id is not None

        # 4. Check active conversation again (creating a new one should auto-activate it)
        resp_act_after_create = await client.get(f"{SERVER_URL}/conversations/active")
        assert resp_act_after_create.status_code == 200
        assert resp_act_after_create.json().get("conversation_id") == conv_a_id, "Newly created conversation should become active"

        # 5. Upload screenshot (should go to "测试对话 A")
        print("[Test] Uploading screenshot to active conversation A...")
        with open(img_path, "rb") as f:
            resp_up = await client.post(
                f"{SERVER_URL}/upload",
                files={"file": ("test_img.png", f, "image/png")}
            )
        assert resp_up.status_code == 200
        up_data = resp_up.json()
        capture_id = up_data.get("capture_id")
        associated_conv = up_data.get("conversation_id")
        print(f"[Test] Uploaded image. Capture ID: {capture_id}, associated conv: {associated_conv}")
        assert associated_conv == conv_a_id, "Uploaded image must belong to the active conversation A"

        # 6. Stream SSE AI response
        print(f"[Test] Connecting to SSE stream for capture {capture_id}...")
        async with client.stream("GET", f"{SERVER_URL}/stream/{capture_id}") as stream_resp:
            assert stream_resp.status_code == 200
            async for line in stream_resp.aiter_lines():
                if line.startswith("data:"):
                    event_data = line[5:].strip()
                    try:
                        parsed = json.loads(event_data)
                        text = parsed.get("text", "")
                        done = parsed.get("done", False)
                        if text:
                            print(text, end="", flush=True)
                        if done:
                            print("\n[Test] Stream delivery complete.")
                            break
                    except Exception as e:
                        print(f"\n[Test] Parse error: {e}")

        # 7. Create another conversation: "测试对话 B"
        resp_new_b = await client.post(
            f"{SERVER_URL}/conversations",
            data={"title": "测试对话 B"}
        )
        assert resp_new_b.status_code == 200
        conv_b_id = resp_new_b.json().get("conversation_id")
        print(f"[Test] Created '测试对话 B' ID: {conv_b_id}")

        # 8. Check captures list in A vs B
        # A should have 1 capture
        resp_caps_a = await client.get(f"{SERVER_URL}/conversations/{conv_a_id}/captures")
        assert resp_caps_a.status_code == 200
        caps_a = resp_caps_a.json()
        print(f"[Test] Number of captures in conversation A: {len(caps_a)}")
        assert len(caps_a) == 1

        # B should have 0 captures
        resp_caps_b = await client.get(f"{SERVER_URL}/conversations/{conv_b_id}/captures")
        assert resp_caps_b.status_code == 200
        caps_b = resp_caps_b.json()
        print(f"[Test] Number of captures in conversation B: {len(caps_b)}")
        assert len(caps_b) == 0

        # 9. Test deletion of conversation A (which should clean up images)
        print(f"[Test] Deleting conversation A ({conv_a_id})...")
        resp_del_a = await client.delete(f"{SERVER_URL}/conversations/{conv_a_id}")
        assert resp_del_a.status_code == 200
        
        # Verify captures inside A are gone (deleted from DB due to CASCADE)
        # We can try to list captures or verify that history is empty
        resp_caps_a_after = await client.get(f"{SERVER_URL}/conversations/{conv_a_id}/captures")
        assert len(resp_caps_a_after.json()) == 0, "All captures of conversation A should be cascade deleted"
        print("[Test] Cascade deletion verified successfully.")

        # Clean up conversation B
        print(f"[Test] Deleting conversation B ({conv_b_id})...")
        await client.delete(f"{SERVER_URL}/conversations/{conv_b_id}")

    # Remove temporary dummy image
    try:
        os.remove(img_path)
        os.rmdir("test_temp_overhaul")
    except Exception:
        pass

    print("=============================================================")
    print("[Overhaul Test] ALL TESTS PASSED SUCCESSFULLY!")
    print("=============================================================")

if __name__ == "__main__":
    asyncio.run(test_overhaul_flow())
