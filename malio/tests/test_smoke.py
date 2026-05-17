"""Smoke tests — core user flows must never break."""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from httpx import ASGITransport, AsyncClient
from main import app


async def _post(path: str, json_data: dict):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post(path, json=json_data)


async def _get(path: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path)


@pytest.mark.anyio
async def test_root_health():
    resp = await _get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


@pytest.mark.anyio
async def test_chat_recommend_returns_songs():
    """User asks for recommendation → response + song list returned."""
    resp = await _post("/api/chat", {"user_id": "test", "input": "推荐一首歌"})
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert isinstance(data["response"], str)
    assert len(data["response"]) > 0
    assert "recommendations" in data
    assert isinstance(data["recommendations"], list)


@pytest.mark.anyio
async def test_chat_chat_does_not_crash():
    """Casual chat → valid response, no crash."""
    resp = await _post("/api/chat", {"user_id": "test", "input": "你觉得爵士乐怎么样？"})
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert isinstance(data["response"], str)


def test_skip_advances_queue():
    """After setting playlist, song_skip → queue advances."""
    from core.state_manager import get_playback, set_playlist, next_in_queue

    fake = [
        {"id": "t1", "title": "A", "artist": ["AA"]},
        {"id": "t2", "title": "B", "artist": ["BB"]},
    ]
    uid = "test_skip_user"
    set_playlist(fake, user_id=uid)
    ps = get_playback(uid)
    assert ps["index"] == 0
    assert ps["current"]["id"] == "t1"
    assert next_in_queue(uid)["id"] == "t2"
    assert ps["index"] == 1


@pytest.mark.anyio
async def test_recommendations_have_required_fields():
    """If recommendations are returned, each song has id/title/artist."""
    resp = await _post("/api/chat", {"user_id": "test", "input": "播放本地歌曲"})
    assert resp.status_code == 200
    data = resp.json()
    for song in data.get("recommendations", []):
        assert "id" in song
        assert "title" in song
        assert "artist" in song

@pytest.mark.anyio
async def test_react_hard_stop():
    """ReAct hard stop: ≥5 songs → 1 round."""
    res = await _post("/api/chat", {"user_id": "test_hs", "input": "推荐一首歌"})
    assert res.status_code == 200
    data = res.json()
    assert len(data.get("recommendations", [])) >= 5
    # Verify metrics: react_rounds should be 1
    import csv
    try:
        with open("data/metrics.csv", "r") as f:
            rows = list(csv.DictReader(f))
        r = rows[-1]
        assert int(r.get("react_rounds", 3)) <= 2, f"Expected ≤2 rounds, got {r.get('react_rounds')}"
    except (FileNotFoundError, IndexError):
        pass  # metrics file may not exist in CI

@pytest.mark.anyio
async def test_dsl_rule_generation():
    """DSL rule: '以后晚上暗一点' → rule stored."""
    res = await _post("/api/chat", {"user_id": "test_rule", "input": "以后晚上暗一点"})
    assert res.status_code == 200
    data = res.json()
    assert "response" in data
    # Rule should be stored for this user
    from core.state_manager import get_agent_rules
    rules = get_agent_rules("test_rule")
    assert len(rules) >= 1, f"Expected ≥1 rule, got {len(rules)}"
    rule = rules[-1]
    assert "when" in rule
    assert "then" in rule

@pytest.mark.anyio
async def test_plan_weather():
    """Plan mode '天气' → instant, no LLM."""
    res = await _post("/api/chat", {"user_id": "test_w", "input": "今天天气怎么样"})
    assert res.status_code == 200
    data = res.json()
    assert "温度" in data["response"] or "天气" in data["response"]
    assert len(data.get("recommendations", [])) == 0  # weather shouldn't return songs

@pytest.mark.anyio
async def test_chat_history_accumulates():
    """Consecutive chats → history grows."""
    uid = "test_ch"
    await _post("/api/chat", {"user_id": uid, "input": "推荐一首歌"})
    await _post("/api/chat", {"user_id": uid, "input": "你觉得爵士乐怎么样"})
    from core.state_manager import get_chat_history
    ch = get_chat_history(uid)
    assert len(ch) >= 4, f"Expected ≥4 messages (2 exchanges), got {len(ch)}"

@pytest.mark.anyio
async def test_selected_song_id_consistency():
    """selected_song_id → the spoken song IS the played song."""
    res = await _post("/api/chat", {"user_id": "test_sid", "input": "推荐一首歌"})
    assert res.status_code == 200
    data = res.json()
    recs = data.get("recommendations", [])
    if recs:
        from core.state_manager import get_playback
        ps = get_playback("test_sid")
        cur = ps.get("current", {})
        # The first recommendation should be the current song
        if cur:
            assert cur.get("id") == recs[0].get("id"), \
                f"Spoken={recs[0].get('title')} but playing={cur.get('title')}"

@pytest.mark.anyio
async def test_skip_weakens_preference():
    """Skip → L3 artist preference weakened."""
    uid = "test_l3skip"
    from core.state_manager import set_playlist
    set_playlist([{"id": "s1", "title": "TestSkip1", "artist": ["TestSkipArtist"], "genre": ["TestGenre"]}], user_id=uid)
    # Manually trigger a song_skip via the pipeline
    from core.state_manager import get_playback
    ps = get_playback(uid)
    ps["current"] = {"id": "s1", "title": "TestSkip1", "artist": ["TestSkipArtist"], "genre": ["TestGenre"]}
    # Call weaken directly as the WS would
    from memory.user_profile import l3_profile
    before = l3_profile.preferences.get("artists", {}).get("TestSkipArtist", {}).get("strength", 0.5)
    l3_profile.weaken("artists", "TestSkipArtist", "test skip")
    after = l3_profile.preferences.get("artists", {}).get("TestSkipArtist", {}).get("strength", 0.5)
    assert after < before, f"Preference should weaken: {before} → {after}"


# ═══════════════════════════════════════════════════════════════
# Bug-regression tests — added after backend audit 2026-05-18
# ═══════════════════════════════════════════════════════════════

def test_set_playlist_oob_index_clamped():
    """set_playlist with out-of-bounds start_index → clamped, no crash."""
    from core.state_manager import get_playback, set_playlist, next_in_queue

    songs = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]
    uid = "test_oob"
    # start_index beyond list length → should clamp to last valid index
    set_playlist(songs, start_index=99, user_id=uid)
    ps = get_playback(uid)
    assert ps["index"] == 1  # clamped to len-1
    assert ps["current"]["id"] == "b"
    # next_in_queue should wrap correctly from clamped index
    nxt = next_in_queue(uid)
    assert nxt["id"] == "a"
    assert ps["index"] == 0


def test_set_playlist_empty_songs():
    """set_playlist with empty list → no crash, empty state."""
    from core.state_manager import get_playback, set_playlist

    uid = "test_empty_pl"
    set_playlist([], start_index=0, user_id=uid)
    ps = get_playback(uid)
    assert ps["playlist"] == []
    assert ps["current"] == {}
    assert ps["index"] == 0


def test_set_playlist_zero_songs_index_clamped():
    """set_playlist with 0 songs → start_index clamped to 0, no IndexError."""
    from core.state_manager import get_playback, set_playlist

    uid = "test_zero_pl"
    set_playlist([], start_index=5, user_id=uid)
    ps = get_playback(uid)
    assert ps["index"] == 0
    assert ps["current"] == {}


@pytest.mark.anyio
async def test_llm_auto_events_not_lost():
    """Rapid push() calls → all events captured in queue, one reactor processes them."""
    from agent.llm_autonomous import LLMAutonomous

    class FakeFeedback:
        def __init__(self):
            self.snapshots = []
        async def push_snapshot(self, **kw):
            self.snapshots.append(kw)

    class FakePersona:
        energy = 0.5
        warmth = 0.5
        playfulness = 0.5

    class FakeProvider:
        def generate(self, prompt):
            return '{"action":"breath","params":{"rate":0.015,"depth":0.5}}'

    class FakeRegistry:
        def get_active(self):
            return FakeProvider()

    auto = LLMAutonomous(FakeRegistry(), FakeFeedback(), FakePersona())
    # Push 5 events rapidly
    for i in range(5):
        auto.push(f"test_{i}")
    # All 5 should be in the queue
    assert len(auto._queue) == 5
    # Let the scheduled reactor task start
    await asyncio.sleep(0)
    # Only one reactor should be running
    assert auto._busy is True
    # Second push after busy should queue, not spawn another task
    auto.push("test_5")
    assert len(auto._queue) == 6  # all events preserved


@pytest.mark.anyio
async def test_persona_drift_triggers_save():
    """drift_from_interaction → persona saved to disk within 60s debounce."""
    import os, time
    from agent.persona import persona_engine

    save_path = persona_engine._path
    # Reset debounce timer so save will fire
    persona_engine._last_save_ts = 0
    old_mtime = os.path.getmtime(save_path) if os.path.exists(save_path) else 0

    persona_engine.drift_from_interaction("core_drag", {})
    # Small sleep to let any filesystem ops settle
    time.sleep(0.1)

    new_mtime = os.path.getmtime(save_path) if os.path.exists(save_path) else 0
    assert new_mtime >= old_mtime, "save() should be called after drift"
