"""MusicAgent — music reasoning worker with its own ReAct loop.

Router delegates music tasks → MusicAgent runs ReAct independently →
returns structured result. No user dialogue — only speaks through Router.
"""
import json
from typing import Dict, Any, List


class MusicAgent:
    """Handles music search, recommendation, and DJ reasoning."""

    def __init__(self, recommendation_engine, netease_integration, tool_registry,
                 provider_registry=None, reasoner=None, feedback_mgr=None):
        self.engine = recommendation_engine
        self.netease = netease_integration
        self.tool_registry = tool_registry
        self.provider_registry = provider_registry
        self.reasoner = reasoner
        self.feedback_mgr = feedback_mgr

    # ── Tool execution ────────────────────────────────────────

    def search(self, query: str, limit: int = 5) -> dict:
        tracks = self.netease.search_tracks(query, limit) or []
        return {"songs": tracks}

    def recommend(self, user_id: str = "default", limit: int = 5) -> dict:
        recs = self.engine.get_contextual_recommendations(user_id, limit) or []
        return {"songs": recs}

    def get_local_songs(self, limit: int = 80) -> dict:
        from core.state_manager import query_local_songs
        return {"songs": query_local_songs(limit, self.engine)}

    def execute_tool(self, tool_name: str, args: dict) -> dict:
        from core.state_manager import enrich_songs

        if tool_name == "search_music":
            raw = self.search(args.get("query", ""), args.get("limit", 5))
            raw["songs"] = enrich_songs(raw.get("songs", []), self.engine)
            return raw
        if tool_name == "get_local_songs":
            return self.get_local_songs(args.get("limit", 80))
        if tool_name == "get_recommendations":
            return self.recommend(args.get("user_id", "default"), args.get("limit", 5))
        if tool_name == "get_lyrics":
            return {"lyrics": f"lyrics for {args.get('title','')}"}
        if tool_name in ("check_history", "get_current_song", "get_playlist",
                         "get_l2_summary", "get_l3_profile", "get_weather"):
            try:
                result = self.tool_registry.execute(tool_name, args)
                # Normalize: wrap list results in dict
                if isinstance(result, list):
                    result = {"songs": result}
                return result if isinstance(result, dict) else {"data": result}
            except Exception:
                return {}
        return {"error": f"Unknown tool: {tool_name}"}

    # ── ReAct reasoning (delegated by Router) ──────────────────

    async def reason(self, user_input: str, constraints: str = "",
                     perception_ctx: dict = None) -> dict:
        """Run independent ReAct loop for music recommendation.

        Returns: {intent, response, selected_song_id, _react_songs,
                  atmosphere, core_actions, reasoning}
        """
        if not self.provider_registry or not self.reasoner:
            return {"response": "抱歉，音乐服务暂不可用。", "intent": "unknown",
                    "_react_songs": [], "selected_song_id": ""}

        provider = self.provider_registry.get_active()
        if not provider:
            return {"response": "抱歉，音乐服务暂不可用。", "intent": "unknown",
                    "_react_songs": [], "selected_song_id": ""}

        ctx = perception_ctx or {}
        ctx["_music_constraints"] = constraints

        MAX_ROUNDS = 3
        all_songs = []
        raw_result = {}

        try:
            sys_prompt = self.reasoner._build_prompt(user_input, ctx)
            sys_prompt += "\n\n你是MusicAgent，只负责选歌。用工具获取歌曲，选出最合适的一首，set selected_song_id。只输出JSON。"
            messages = [{"role": "system", "content": sys_prompt}]

            # Dynamic tools from registry — only music-related ones
            tools = []
            for info in self.tool_registry.get_schema():
                if info["name"] in ("search_music", "get_local_songs", "get_recommendations",
                                    "get_playlist", "get_current_song", "check_history",
                                    "get_l2_summary", "get_l3_profile"):
                    props = {}
                    for pname, ptype in info.get("parameters", {}).items():
                        props[pname] = {"type": _TYPE_MAP.get(ptype, "string")}
                    tools.append({"type": "function", "function": {
                        "name": info["name"], "description": info["description"],
                        "parameters": {"type": "object", "properties": props}}})
            print(f"[MusicAgent] {len(tools)} tools loaded")

            for round_idx in range(MAX_ROUNDS):
                resp = provider.generate_with_tools(messages, tools)
                content = resp.get("content", "") or ""
                tool_calls = resp.get("tool_calls")

                if not tool_calls:
                    raw_result = self.reasoner._parse_response(content)
                    raw_result["_react_songs"] = all_songs
                    if self.feedback_mgr:
                        await self.feedback_mgr.push_agent_log("音乐Agent思考完成")
                    print(f"[MusicAgent] stopped at round {round_idx + 1}")
                    break

                round_songs = []
                tool_names = []
                assistant_msg = {"role": "assistant", "content": content or "", "tool_calls": tool_calls}
                if resp.get("reasoning_content"):
                    assistant_msg["reasoning_content"] = resp["reasoning_content"]
                messages.append(assistant_msg)

                for tc in tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    tool_names.append(fn_name)
                    fn_args = json.loads(fn.get("arguments", "{}"))
                    tool_result = self.execute_tool(fn_name, fn_args)
                    songs = tool_result.get("songs", []) or tool_result.get("tracks", []) or []
                    round_songs.extend(songs)
                    slim = {"songs": [{"id": s["id"], "title": s["title"],
                             "artist": s["artist"], "lang": s.get("lang", "en")}
                            for s in songs]} if songs else tool_result
                    messages.append({"role": "tool", "tool_call_id": tc.get("id", "call_1"),
                                     "content": json.dumps(slim, ensure_ascii=False)[:6000]})

                all_songs.extend(round_songs)
                print(f"[MusicAgent] 第{round_idx + 1}轮: {', '.join(tool_names)} → {len(round_songs)}首歌")

                # Hard stop: got enough songs
                if all_songs and round_idx < MAX_ROUNDS - 1 and len(all_songs) >= 5:
                    messages.append({"role": "user",
                        "content": f"已获取 {len(all_songs)} 首歌，完全足够。请现在直接输出最终JSON（不要再调工具），选中一首并把ID填入selected_song_id。"})
                    raw_resp = provider.generate_with_tools(messages, tools)
                    raw_text = raw_resp.get("content", "") if isinstance(raw_resp, dict) else raw_resp
                    raw_result = self.reasoner._parse_response(raw_text)
                    if "atmosphere" not in raw_result: raw_result["atmosphere"] = None
                    raw_result["_react_songs"] = all_songs
                    print(f"[MusicAgent] hard stop at round {round_idx + 1}, {len(all_songs)} songs")
                    return _normalize(raw_result, all_songs)

                # Final round forced
                if round_idx == MAX_ROUNDS - 1:
                    messages.append({"role": "user",
                        "content": "最后一轮。请基于以上所有查询结果输出最终JSON回复（不要再调工具）。只输出JSON。"})
                    final_resp = provider.generate_with_tools(messages, tools)
                    final_text = final_resp.get("content", "") if isinstance(final_resp, dict) else str(final_resp)
                    raw_result = self.reasoner._parse_response(final_text)
                    if "atmosphere" not in raw_result: raw_result["atmosphere"] = None
                    raw_result["_react_songs"] = all_songs
                    print(f"[MusicAgent] forced final, total songs: {len(all_songs)}")
                    return _normalize(raw_result, all_songs)

            if not raw_result and content:
                raw_result = self.reasoner._parse_response(content)

        except Exception as e:
            import traceback
            print(f"[MusicAgent] ReAct failed: {e}")
            traceback.print_exc()
            raw_result = {"response": "抱歉，音乐推荐遇到问题。"}

        return _normalize(raw_result, all_songs)


_TYPE_MAP = {"int": "integer", "string": "string", "float": "number",
              "bool": "boolean", "list": "array", "dict": "object"}


def _normalize(raw: dict, songs: list) -> dict:
    return {
        "response": raw.get("response", ""),
        "intent": raw.get("intent", "music_recommendation"),
        "reasoning": raw.get("reasoning", ""),
        "actions": raw.get("actions", []),
        "core_actions": raw.get("core_actions", []),
        "selected_song_id": raw.get("selected_song_id", ""),
        "atmosphere": raw.get("atmosphere", None),
        "_react_songs": raw.get("_react_songs", songs),
    }
