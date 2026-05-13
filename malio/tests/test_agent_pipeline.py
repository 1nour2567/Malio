"""Integration tests for the 5-stage agent pipeline."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.perception import Perception
from agent.router import Router
from agent.tools import ToolRegistry
from agent.feedback import Feedback
from agent.providers import ProviderRegistry, OpenAICompatibleProvider


def test_perception_builds_context():
    p = Perception()
    result = p.build("Hello")
    assert "user_input" in result, "Missing 'user_input' in perception result"
    assert "time" in result, "Missing 'time' in perception result"
    tod = result["time"]["time_of_day"]
    assert tod in ("morning", "afternoon", "evening", "night"), \
        f"Invalid time_of_day: {tod}"
    print("[PASS] test_perception_builds_context")


def test_router_direct_commands():
    r = Router()
    assert r.route("play")["routed_to"] == "direct"
    assert r.route("next")["routed_to"] == "direct"
    assert r.route("你好")["routed_to"] == "reasoning"
    print("[PASS] test_router_direct_commands")


def test_tool_registry():
    tr = ToolRegistry()
    tr.register(
        name="echo",
        description="Echo back the input",
        parameters={"msg": "string"},
        handler=lambda msg: {"echo": msg},
    )
    tools = tr.list_tools()
    names = [t["name"] for t in tools]
    assert "echo" in names, "echo tool not found in list_tools"
    result = tr.execute("echo", {"msg": "hello"})
    assert result == {"echo": "hello"}, f"Unexpected echo result: {result}"
    print("[PASS] test_tool_registry")


def test_tool_missing_returns_error():
    tr = ToolRegistry()
    result = tr.execute("nonexistent", {})
    assert "error" in result, "Missing 'error' for nonexistent tool"
    print("[PASS] test_tool_missing_returns_error")


def test_feedback_builds_snapshot():
    fb = Feedback()
    snapshot = fb.build_snapshot(
        song="test_song",
        playlist=["track1", "track2"],
        is_playing=True,
        agent_log="test log",
        tool_error=None,
    )
    assert snapshot["type"] == "state_snapshot", \
        f"Expected type='state_snapshot', got {snapshot['type']}"
    assert snapshot["seq"] == 1, f"Expected seq=1, got {snapshot['seq']}"
    assert "tool_error" in snapshot, "Missing 'tool_error' key in snapshot"
    assert "song" in snapshot
    assert "playlist" in snapshot
    assert "is_playing" in snapshot
    assert "agent_log" in snapshot
    print("[PASS] test_feedback_builds_snapshot")


def test_provider_registry():
    reg = ProviderRegistry()
    provider = OpenAICompatibleProvider(
        name="test_provider",
        api_key="test_key",
        base_url="https://api.example.com/v1",
        model="test-model",
    )
    reg.register(provider)
    active = reg.get_active()
    assert active is not None, "get_active() returned None after registering available provider"
    assert active.name == "test_provider", \
        f"Expected provider name 'test_provider', got {active.name}"
    result = reg.set_active("nonexistent_provider")
    assert result is False, "set_active to nonexistent provider should return False"
    print("[PASS] test_provider_registry")


if __name__ == "__main__":
    test_perception_builds_context()
    test_router_direct_commands()
    test_tool_registry()
    test_tool_missing_returns_error()
    test_feedback_builds_snapshot()
    test_provider_registry()
    print("\nAll agent pipeline tests passed!")
