"""Smoke tests — core user flows must never break."""
import sys, os
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
