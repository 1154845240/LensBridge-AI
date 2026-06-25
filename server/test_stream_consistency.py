import asyncio
import json
import tempfile
from pathlib import Path

from server import app as app_module
from server import database


async def consume_stream(response):
    events = []
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        for line in text.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


async def main():
    original_db_path = database.DB_PATH
    original_call = app_module.agent_manager.call_agent_stream
    original_config_path = app_module.agent_manager.CONFIG_PATH
    calls = []

    async def fake_call(image_paths, user_prompt="", agent_name=None):
        calls.append(agent_name)
        for part in ("same ", "answer"):
            await asyncio.sleep(0.03)
            yield part

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            database.DB_PATH = str(Path(temp_dir) / "test.db")
            database.init_db()
            conversation_id = database.get_conversations()[0]["id"]
            capture_id = database.add_capture(conversation_id, "", "gemini")
            app_module.agent_manager.call_agent_stream = fake_call
            app_module.capture_tasks.clear()

            first = await app_module.stream_capture(capture_id)
            second = await app_module.stream_capture(capture_id)
            first_events, second_events = await asyncio.gather(
                consume_stream(first),
                consume_stream(second),
            )

            def combined(events):
                return "".join(event.get("text", "") for event in events)

            assert calls == ["gemini"], calls
            assert combined(first_events) == "same answer"
            assert combined(second_events) == "same answer"
            assert all(
                event.get("agent") == "gemini"
                for event in first_events + second_events
                if "agent" in event
            )

            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps({"active_agent": "deepseek", "agents": {}}),
                encoding="utf-8",
            )
            app_module.agent_manager.CONFIG_PATH = str(config_path)
            database.reset_capture_analysis(capture_id, "gemini")
            config_path.write_text(
                json.dumps({"active_agent": "deepseek", "agents": {}}),
                encoding="utf-8",
            )
            result = await app_module.retry_capture(capture_id)
            assert result["agent_name"] == "deepseek"
            assert database.get_capture(capture_id)["agent_name"] == "deepseek"
    finally:
        database.DB_PATH = original_db_path
        app_module.agent_manager.call_agent_stream = original_call
        app_module.agent_manager.CONFIG_PATH = original_config_path
        app_module.capture_tasks.clear()


if __name__ == "__main__":
    asyncio.run(main())
    print("Stream consistency test OK")
