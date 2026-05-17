"""5-stage Agent pipeline: Perception → Router → Reasoner → Tools → Feedback."""
import json
import asyncio
import collections
import datetime as dt
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

MUSIC_INTENTS = ("music_recommendation", "mood_change", "command")


class MusicResponse(BaseModel):
    response: str
    recommendations: List[Dict[str, Any]] = []
    auto_play: bool = False


class Pipeline:
    """Encapsulates the full chat pipeline. All heavy deps injected at init."""

    def __init__(self, perception, router, reasoner, provider_registry, tool_registry,
                 feedback_mgr, recommendation_engine, device_control,
                 l2_memory, l3_profile, persona_engine,
                 scene_engine=None, music_agent=None, visual_agent=None):
        self.perception = perception
        self.router = router
        self.reasoner = reasoner
        self.provider_registry = provider_registry
        self.tool_registry = tool_registry
        self.feedback_mgr = feedback_mgr
        self.recommendation_engine = recommendation_engine
        self.device_control = device_control
        self.l2_memory = l2_memory
        self.l3_profile = l3_profile
        self.persona_engine = persona_engine
        self.scene_engine = scene_engine
        self.music_agent = music_agent
        self.visual_agent = visual_agent

    async def run(self, request) -> 'MusicResponse':
        """Main entry point — called by /api/chat route."""

        self._current_user_id = getattr(request, 'user_id', None) or "default"

        try:
            # Stage 1: Perception
            print("[chat] Stage 1: Perception...")
            perception_ctx = self.perception.build(request.input, request.user_id)
            if request.context:
                perception_ctx["context"] = request.context

            from core.state_manager import get_core_events, get_chat_history, get_agent_rules
            from memory.short_term import l2_memory
            from memory.user_profile import l3_profile
            from agent.persona import persona_engine

            uid = self._current_user_id
            if get_core_events(uid):
                perception_ctx["core_events"] = list(get_core_events(uid))[-10:]
            perception_ctx["l2_summary"] = self.l2_memory.summary_for_prompt()
            perception_ctx["l3_profile"] = self.l3_profile.summary_for_prompt(perception_ctx.get("time", {}))
            perception_ctx["chat_history"] = list(get_chat_history(uid))
            perception_ctx["persona_style"] = self.persona_engine.style_for_prompt()
            perception_ctx["persona_drift_log"] = self.persona_engine.drift_log_for_prompt()
            perception_ctx["agent_active_rules"] = list(get_agent_rules(uid))

            # Stage 2: Router
            print("[chat] Stage 2: Router...")
            classification = self.router.classify(request.input)
            mode = classification.get("mode", "agent")
            print(f"[chat] Mode: {mode}")

            # ── PLAN ──
            if mode == "plan":
                return self._handle_plan(classification)

            # ── DIRECT COLOR ──
            if mode == "direct_color":
                from datetime import datetime
                now = datetime.now()
                tod = "morning" if 5 <= now.hour < 12 else "afternoon" if 12 <= now.hour < 18 else "evening" if 18 <= now.hour < 22 else "night"
                atm = self.persona_engine.derive_atmosphere(tod, now.hour)
                await self.feedback_mgr.push_snapshot(
                    core_action={"action": "set_color", "params": {"color": classification["color"]}},
                    atmosphere=atm)
                return MusicResponse(response="换好了，{}。".format(classification["color_name"]), recommendations=[], auto_play=False)

            # ── YOLO ──
            if mode == "yolo":
                return await self._handle_yolo(request, perception_ctx, classification)

            # ── AGENT (default) ──
            return await self._handle_agent(request, perception_ctx)

        except Exception as e:
            import traceback
            print(f"[chat] ERROR: {e}")
            print(f"[chat] Full traceback:\n{traceback.format_exc()}")
            await self.feedback_mgr.push_snapshot(core_mode="error", agent_log=f"错误: {e}")
            return MusicResponse(
                response=f"抱歉，我遇到了一些问题。\n错误类型：{type(e).__name__}",
                recommendations=[]
            )

    # ── PLAN branch ────────────────────────────────────────────

    def _handle_plan(self, classification: dict) -> 'MusicResponse':

        from core.state_manager import query_local_songs, get_playback
        from memory.short_term import l2_memory
        source = classification.get("plan_source", "")

        if source == "local_lookup":
            songs = query_local_songs(200, self.recommendation_engine)
            return MusicResponse(
                response=f"本地曲库共 {len(songs)} 首: " + ", ".join(
                    f"{s['title']}({', '.join(s['artist'])})" for s in songs[:20]),
                recommendations=songs, auto_play=False)

        if source == "history":
            return MusicResponse(response=self.l2_memory.today_summary(), recommendations=[])

        if source == "weather" and self.scene_engine:
            w = self.scene_engine.get_weather_context(24.9175, 118.6465) or {}
            return MusicResponse(
                response=f"天气: {w.get('description','未知')}, 温度: {w.get('temperature','?')}°C (体感 {w.get('feels_like','?')}°C), "
                         f"湿度: {w.get('humidity','?')}%, 气压: {w.get('pressure','?')} hPa, "
                         f"风速: {w.get('wind_speed','?')} m/s (阵风 {w.get('wind_gust','?')} m/s), "
                         f"能见度: {w.get('visibility','?')} m, 云量: {w.get('clouds','?')}%, "
                         f"日出: {w.get('sunrise') and __import__('datetime').datetime.fromtimestamp(w['sunrise']).strftime('%H:%M') or '?'}, "
                         f"日落: {w.get('sunset') and __import__('datetime').datetime.fromtimestamp(w['sunset']).strftime('%H:%M') or '?'}",
                recommendations=[])

        if source == "status":
            s = get_playback(self._current_user_id).get("current", {})
            if s:
                return MusicResponse(response=f"正在播放: {s.get('title','?')} — {', '.join(s.get('artist',[]))}", recommendations=[])
            return MusicResponse(response="当前没有正在播放的歌曲", recommendations=[])

        return MusicResponse(response="无法处理该请求", recommendations=[])

    # ── YOLO branch ─────────────────────────────────────────────

    # Whitelist: YOLO auto-executes only read-only tools
    YOLO_ALLOWED = {"search_music", "get_local_songs", "get_recommendations",
                    "check_history", "get_current_song", "get_playlist",
                    "get_weather", "get_l2_summary", "get_l3_profile", "get_lyrics"}

    async def _handle_yolo(self, request, perception_ctx: dict, classification=None) -> 'MusicResponse':

        from core.state_manager import set_playlist, get_playback

        uid = self._current_user_id

        # Full reset: actually clear L3 profile
        if classification and classification.get("reset_all"):
            self.l3_profile.preferences = {"artists":{},"genres":{},"eras":{},"disliked_artists":{},"disliked_genres":{},"time_slots":{},"_pending":[]}
            self.l3_profile.behavior = {"avg_skip_time_sec":180,"avg_volume":70,"preferred_play_mode":"shuffle","peak_hours":[],"session_duration_avg":30}
            self.l3_profile.mood = {"baseline":"neutral","patterns":{},"mood_swing_hours":[]}
            self.l3_profile.rules = {"explicit":[],"inferred":[],"active_dsl_ids":[]}
            self.l3_profile._save()
            return MusicResponse(response="全部清空了。现在是一张白纸，想让我重新认识你吗？", recommendations=[], auto_play=False)

        # Rule command: quick LLM ack → extract rules from text, skip song tools
        if classification and classification.get("rule_command"):
            provider = self.provider_registry.get_active()
            if provider:
                sys_prompt = self.reasoner._build_prompt(request.input, perception_ctx)
                sys_prompt += "\n\n你正在处理用户的持久规则请求。你必须输出JSON（不是纯文本），在rules字段中指定when-then。response只需一句话确认。不要调工具，不要歌曲。只输出JSON。"
                raw = provider.generate(sys_prompt)
                result = self.reasoner._parse_response(raw)
            else:
                result = {"response": "好的，已记下。", "intent": "command"}

            # Store + broadcast extracted rules
            from core.state_manager import get_agent_rules
            new_rules = result.get("rules") or []
            stored = get_agent_rules(uid)
            for rule in new_rules:
                rule["source"] = "agent"
                rule.setdefault("id", f"agent_{int(dt.datetime.now().timestamp())}")
                rule["created_at"] = dt.datetime.now().isoformat()
                while len(stored) >= 3:
                    removed = stored.pop(0)
                    print(f"[rules] evicted {removed.get('id')}")
                stored.append(rule)
                await self.feedback_mgr.push_rule(rule)
                print(f"[rules] agent created: {rule.get('id')} — {rule.get('note', '')[:60]}")

            return MusicResponse(response=result.get("response", "已记录"), recommendations=[], auto_play=False)

        result = await _react_loop(self, perception_ctx, request.input)
        # Filter actions to whitelist only
        actions = result.get("actions", [])
        allowed_actions = [a for a in actions
                          if isinstance(a, dict) and a.get("tool", "") in self.YOLO_ALLOWED]
        if len(allowed_actions) < len(actions):
            print(f"[yolo] filtered {len(actions) - len(allowed_actions)} non-whitelisted actions")
        result["actions"] = allowed_actions

        recs = result.get("_react_songs", [])
        if recs:
            set_playlist(recs, user_id=uid)
            current = get_playback(self._current_user_id)["current"]
            response_text = f"🎵 {current.get('title','')} — {', '.join(current.get('artist',[]))}\n\n{result.get('response','')}"
        else:
            response_text = result.get("response", "已完成")
        return MusicResponse(response=response_text, recommendations=recs, auto_play=bool(recs))

    # ── AGENT branch (5-stage pipeline) ─────────────────────────

    async def _handle_agent(self, request, perception_ctx: dict) -> 'MusicResponse':

        from core.state_manager import (get_playback, set_playlist,
                                         get_core_events, get_chat_history, state_store,
                                         get_agent_rules)

        uid = self._current_user_id
        route_result = self.router.route(request.input)
        agent_log = ""

        # Direct commands — skip LLM
        if route_result["routed_to"] == "direct":
            return self._handle_direct(route_result, agent_log)

        # Stage 3: Reasoner — delegate music to MusicAgent if available
        print("[chat] Stage 3: Reasoner...")
        await self.feedback_mgr.push_snapshot(core_mode="vortex", agent_log="思考中...")
        async def _pulse_vortex():
            for _ in range(3):
                await asyncio.sleep(1.5)
                try: await self.feedback_mgr.push_snapshot(core_mode="vortex")
                except: pass
        asyncio.create_task(_pulse_vortex())

        # ── MusicAgent delegation ──
        is_music = any(kw in request.input.lower() for kw in
                       ["推荐", "来一首", "听听", "放首歌", "歌", "音乐", "播放", "放点"])
        if self.music_agent and self.music_agent.provider_registry and is_music:
            reasoner_result = await self.music_agent.reason(
                request.input, perception_ctx=perception_ctx)
        else:
            reasoner_result = await _react_loop(self, perception_ctx, request.input)
        agent_log = reasoner_result.get("reasoning", "")
        response_text = reasoner_result.get("response", "好的，让我为您推荐一些音乐。")

        # Stage 4: Tools
        print("[chat] Stage 4: Tools...")
        recommendations = reasoner_result.get("_react_songs", [])
        if not recommendations:
            for action in reasoner_result.get("actions", []):
                if isinstance(action, dict):
                    tr = self.tool_registry.execute(action.get("tool", ""), action.get("params", {}))
                    if "error" not in tr:
                        recommendations = tr.get("tracks", []) or tr.get("songs", []) or []

        if not reasoner_result.get("_react_songs") and not reasoner_result.get("actions"):
            reasoner_result["intent"] = "general_chat"
        if not recommendations and reasoner_result.get("intent") in MUSIC_INTENTS:
            recommendations = self.recommendation_engine.get_contextual_recommendations(request.user_id, 5) or []

        # Stage 5: Feedback
        print("[chat] Stage 5: Feedback...")
        core_actions = self.persona_engine.constrain_core_actions(
            reasoner_result.get("core_actions", []) or [])
        for ca in core_actions:
            if ca.get("action"):
                await self.feedback_mgr.push_snapshot(core_action={"action": ca["action"], "params": ca.get("params", {})})

        # ── DSL Rules: validate + broadcast + enforce 3-rule limit ──
        agent_rules = reasoner_result.get("rules") or []
        stored_rules = get_agent_rules(uid)
        for rule in agent_rules:
            if not isinstance(rule, dict):
                continue
            if not rule.get("when") or not rule.get("then"):
                continue
            rule["source"] = "agent"
            rule["id"] = rule.get("id", f"agent_{int(dt.datetime.now().timestamp())}")
            rule["created_at"] = dt.datetime.now().isoformat()
            # Enforce 3-rule limit: evict oldest
            while len(stored_rules) >= 3:
                removed = stored_rules.pop(0)
                print(f"[rules] evicted {removed.get('id')} (limit reached)")
            stored_rules.append(rule)
            await self.feedback_mgr.push_rule(rule)
            print(f"[rules] agent created: {rule.get('id')} — {rule.get('note', '')}")

        should_play = bool(recommendations) and reasoner_result.get("intent") in MUSIC_INTENTS
        if should_play:
            self.persona_engine.drift_from_recommendation()
        if recommendations:
            selected_id = reasoner_result.get("selected_song_id", "")
            if selected_id:
                for i, song in enumerate(recommendations):
                    if song.get("id") == selected_id:
                        if i != 0:
                            recommendations.insert(0, recommendations.pop(i))
                        break
            set_playlist(recommendations, user_id=uid)
            get_playback(self._current_user_id)["is_playing"] = should_play
            if should_play:
                current = get_playback(self._current_user_id)["current"]
                response_text = f"🎵 {current.get('title','')} — {', '.join(current.get('artist',[]))}\n\n{response_text}"

        # Use LLM atmosphere if present, otherwise derive from persona
        llm_atm = reasoner_result.get("atmosphere")
        if not llm_atm:
            from datetime import datetime
            now = datetime.now()
            tod = "morning" if 5 <= now.hour < 12 else \
                  "afternoon" if 12 <= now.hour < 18 else \
                  "evening" if 18 <= now.hour < 22 else "night"
            llm_atm = self.persona_engine.derive_atmosphere(tod, now.hour)

        # Blend weather into atmosphere
        try:
            w = self.scene_engine.get_weather_context(24.9175, 118.6465) if self.scene_engine else {}
            llm_atm = self.persona_engine.blend_weather(llm_atm or {}, w or {})
        except Exception:
            pass

        await self.feedback_mgr.push_snapshot(
            core_mode="dot", agent_log=agent_log,
            song=get_playback(self._current_user_id)["current"] if get_playback(self._current_user_id)["current"] else None,
            playlist=recommendations, is_playing=should_play,
            tool_error=reasoner_result.get("error"),
            atmosphere=llm_atm,
        )
        get_chat_history(uid).append({"role": "user", "content": request.input})
        get_chat_history(uid).append({"role": "agent", "content": response_text})
        state_store.mark_dirty(uid)
        state_store.save(uid)  # persist immediately after each chat

        # ── Metrics ──────────────────────────────────────
        from core.metrics import metrics
        input_lower = request.input.lower()
        metrics.record({
            "ts": dt.datetime.now().isoformat(),
            "intent": reasoner_result.get("intent", ""),
            "react_rounds": reasoner_result.get("_react_rounds", 1),
            "song_count": len(recommendations),
            "had_songs": bool(recommendations),
            "auto_play": should_play,
            "input_len": len(request.input),
            "input_has_recommend": any(kw in input_lower for kw in ["推荐", "听听", "来一首", "放首歌"]),
            "input_has_skip": any(kw in input_lower for kw in ["切歌", "下一首", "跳过"]),
            "response_len": len(response_text),
        })
        return MusicResponse(response=response_text, recommendations=recommendations, auto_play=should_play)

    def _handle_direct(self, route_result: dict, agent_log: str) -> 'MusicResponse':

        cmd = route_result["command"]
        if cmd == "volume":
            value = route_result["params"].get("value", "50")
            self.device_control.set_volume(int(value) if value.isdigit() else 50)
            response = f"音量已设置为 {value}"
        elif cmd == "play":
            self.device_control.play("")
            response = "正在播放音乐"
        elif cmd == "pause":
            self.device_control.pause()
            response = "音乐已暂停"
        elif cmd == "stop":
            self.device_control.stop()
            response = "音乐已停止"
        else:
            response = f"命令: {cmd}"
        return MusicResponse(response=response, recommendations=[])


# ═══════════════════════════════════════════════════════════════
# ReAct loop (module-level — stateless, uses injected pipeline)
# ═══════════════════════════════════════════════════════════════

def _normalize_result(raw: dict, songs: list, rounds: int = 1) -> dict:
    """Ensure all required fields exist with sensible defaults."""
    return {
        "response": raw.get("response", ""),
        "intent": raw.get("intent", "unknown"),
        "reasoning": raw.get("reasoning", ""),
        "actions": raw.get("actions", []),
        "core_actions": raw.get("core_actions", []),
        "selected_song_id": raw.get("selected_song_id", ""),
        "atmosphere": raw.get("atmosphere", None),
        "_react_songs": raw.get("_react_songs", songs),
        "_react_rounds": rounds,
    }


async def _react_loop(pipeline: Pipeline, perception_ctx: dict, user_input: str) -> dict:
    """True ReAct loop: Reason → Act → Observe, up to 3 rounds.

    Each round LLM sees full conversation history. Can call tools OR stop.
    Intermediate states pushed to frontend via agent_log.
    Hardcoded fallback if all rounds produce zero songs.
    """
    MAX_ROUNDS = 3
    raw_result = {}
    all_songs = []
    rounds_used = 0

    provider = pipeline.provider_registry.get_active()
    if not provider:
        raw_result = pipeline.reasoner.reason(user_input, perception_ctx)

    else:
        try:
            # Dynamic tool schema — read from ToolRegistry, map to OpenAI types
            _TYPE_MAP = {"int": "integer", "string": "string", "float": "number",
                         "bool": "boolean", "list": "array", "dict": "object"}
            tools = []
            for info in pipeline.tool_registry.get_schema():
                props = {}
                for pname, ptype in info.get("parameters", {}).items():
                    props[pname] = {"type": _TYPE_MAP.get(ptype, "string")}
                tools.append({
                    "type": "function",
                    "function": {
                        "name": info["name"],
                        "description": info["description"],
                        "parameters": {"type": "object", "properties": props},
                    }
                })
            print(f"[ReAct] {len(tools)} tools loaded from registry")

            sys_prompt = pipeline.reasoner._build_prompt(user_input, perception_ctx)
            sys_prompt += "\n\n性能提示：推荐歌曲只需 get_local_songs 或 get_recommendations 之一。不要同时调用多个数据源。选最有把握的一个工具，拿到歌就立刻输出JSON。"
            messages = [{"role": "system", "content": sys_prompt}]
            content = ""

            for round_idx in range(MAX_ROUNDS):
                rounds_used = round_idx + 1
                resp = provider.generate_with_tools(messages, tools)
                content = resp.get("content", "") or ""
                tool_calls = resp.get("tool_calls")

                # If model doesn't support function calling (e.g. Kimi k2.5),
                # inject local songs and ask for JSON in one final round
                if not tool_calls and round_idx == 0:
                    from core.state_manager import query_local_songs
                    fallback = query_local_songs(20, pipeline.recommendation_engine)
                    if fallback:
                        all_songs = fallback
                        song_list = "\n".join(
                            f"- [{s['id']}] {s['title']} — {', '.join(s.get('artist',[]))}"
                            for s in fallback[:15])
                        messages.append({"role": "user",
                            "content": f"系统已从本地曲库查询了以下歌曲，请从中选择一首推荐给用户，"
                                       f"将其ID填入selected_song_id字段。回复JSON格式。\n\n## 可用歌曲\n{song_list}"})
                        continue  # retry with song data injected

                if not tool_calls:
                    raw_result = pipeline.reasoner._parse_response(content)
                    raw_result["_react_songs"] = all_songs
                    await pipeline.feedback_mgr.push_agent_log("思考完成")
                    print(f"[ReAct] stopped at round {round_idx + 1}")
                    break

                # ── Execute tools ──────────────────────────
                round_songs = []
                tool_names = []
                assistant_msg = {"role": "assistant", "content": content or "", "tool_calls": tool_calls}
                # DeepSeek thinking mode: must echo reasoning_content back
                if resp.get("reasoning_content"):
                    assistant_msg["reasoning_content"] = resp["reasoning_content"]
                messages.append(assistant_msg)
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    tool_names.append(fn_name)
                    fn_args = json.loads(fn.get("arguments", "{}"))
                    tool_result = _execute_react_tool_static(fn_name, fn_args, pipeline)
                    songs = tool_result.get("songs", []) or tool_result.get("tracks", []) or []
                    round_songs.extend(songs)
                    # Send essential fields to LLM — include lang for filtering
                    slim = {"songs": [{"id": s["id"], "title": s["title"],
                             "artist": s["artist"], "lang": s.get("lang", "en")}
                            for s in songs]} if songs else tool_result
                    messages.append({"role": "tool", "tool_call_id": tc.get("id", "call_1"),
                                     "content": json.dumps(slim, ensure_ascii=False)[:6000]})

                all_songs.extend(round_songs)
                log_msg = f"第{round_idx + 1}轮: {', '.join(tool_names)} → {len(round_songs)}首歌"
                await pipeline.feedback_mgr.push_agent_log(log_msg)
                print(f"[ReAct] {log_msg}")

                # ── Early-stop: ≥5 songs → force Phase 2 (full LLM call, no more tools) ──
                if all_songs and round_idx < MAX_ROUNDS - 1 and len(all_songs) >= 5:
                    messages.append({"role": "user",
                        "content": f"已获取 {len(all_songs)} 首歌，完全足够。请现在直接输出最终JSON（不要再调工具），选中一首并把ID填入selected_song_id。"})
                    raw = provider.generate_with_tools(messages, tools)
                    raw_text = raw.get("content", "") if isinstance(raw, dict) else str(raw)
                    raw_result = pipeline.reasoner._parse_response(raw_text)
                    if "atmosphere" not in raw_result: raw_result["atmosphere"] = None
                    raw_result["_react_songs"] = all_songs
                    print(f"[ReAct] hard stop at round {round_idx + 1}, {len(all_songs)} songs")
                    return _normalize_result(raw_result, all_songs, round_idx + 1)

                # ── Hardcoded fallback: all rounds produced nothing ──
                if round_idx == MAX_ROUNDS - 1 and not all_songs:
                    from core.state_manager import query_local_songs
                    fallback = query_local_songs(5, pipeline.recommendation_engine)
                    if fallback:
                        all_songs = fallback
                        await pipeline.feedback_mgr.push_agent_log(
                            "多次搜索未找到结果，已从本地曲库为你加载备用歌曲")
                        # Let LLM know about the fallback
                        fallback_text = "系统已从本地曲库加载了以下备用歌曲，请基于这些歌曲回复用户：\n"
                        fallback_text += "\n".join(f"- [{s['id']}] {s['title']} — {', '.join(s.get('artist',[]))}"
                                                   for s in fallback[:5])
                        messages.append({"role": "user", "content": fallback_text})

                # Final round: force response
                if round_idx == MAX_ROUNDS - 1:
                    messages.append({"role": "user",
                        "content": "这是最后一轮。你已经查询到了足够的歌曲数据。"
                                   "请从中挑选一首推荐给用户，输出JSON格式（不要再调工具）。"
                                   "必须包含selected_song_id字段，填入你选择的歌曲ID。"
                                   "response字段用中文写一段DJ风格的推荐语（不提及具体歌名）。"
                                   "只输出JSON，不要输出其他内容。"})
                    final_resp = provider.generate_with_tools(messages, tools)
                    final_content = final_resp.get("content", "") or ""
                    raw_result = pipeline.reasoner._parse_response(final_content)
                    if "atmosphere" not in raw_result:
                        raw_result["atmosphere"] = None
                    raw_result["_react_songs"] = all_songs
                    await pipeline.feedback_mgr.push_agent_log("生成回复中...")
                    print(f"[ReAct] forced final at round {round_idx + 1}, total songs: {len(all_songs)}")
                    # early return from forced-final — skip unified return
                    return _normalize_result(raw_result, all_songs, rounds_used)

            # Early stop: ensure fields set
            if not raw_result and content:
                raw_result = pipeline.reasoner._parse_response(content)

        except Exception as e:
            print(f"[ReAct] loop failed with {provider.name}: {e}")
            # Try fallback provider
            fallback = None
            for p in pipeline.provider_registry._providers.values():
                if p is not provider and p.is_available():
                    fallback = p
                    break
            if fallback:
                print(f"[ReAct] retrying with {fallback.name}...")
                try:
                    raw_result = pipeline.reasoner.reason(user_input, perception_ctx)
                except Exception as e2:
                    print(f"[ReAct] fallback also failed: {e2}")
                    raw_result = {"response": "抱歉，我遇到了一点问题，正在为你随机推荐一首歌。"}
            else:
                raw_result = {"response": "抱歉，我遇到了一点问题，正在为你随机推荐一首歌。"}

    return _normalize_result(raw_result, all_songs, rounds_used)


def _execute_react_tool_static(fn_name: str, args: dict, pipeline: Pipeline) -> dict:
    """Execute a tool. Music tools delegated to MusicAgent."""
    try:
        # Music tools → MusicAgent (single-responsibility)
        if fn_name in ("search_music", "get_local_songs", "get_recommendations", "get_lyrics"):
            if pipeline.music_agent:
                return pipeline.music_agent.execute(fn_name, args)
            return {"songs": []}

        # Non-music tools → ToolRegistry
        if fn_name in {t["name"] for t in pipeline.tool_registry.get_schema()}:
            return pipeline.tool_registry.execute(fn_name, args) or {}

        return {"error": f"Unknown tool: {fn_name}"}
    except Exception as e:
        return {"error": str(e)}
