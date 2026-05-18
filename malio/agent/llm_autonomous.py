"""LLM-driven autonomous behavior — context-aware core actions.

Triggered after user interactions (chat, skip).  Debounced 5s.
LLM sees event summary + persona state + time → outputs one core_action.
"""
import json, re, asyncio, sys, random
from collections import deque
from datetime import datetime


class LLMAutonomous:
    """Event-driven LLM reactor. Watches interaction events, triggers LLM."""

    def __init__(self, provider_registry, feedback_mgr, persona_engine):
        self._provider = provider_registry
        self._feedback = feedback_mgr
        self._persona = persona_engine
        self._queue = deque(maxlen=30)
        self._busy = False
        self._last_actions = deque(maxlen=5)
        self._call_count = 0
        self._last_speak_ts = 0           # throttle proactive speech
        self._speak_suppress_until = 0     # cooldown after dismissals
        self._consecutive_dismissed = 0    # consecutive times user ignored speech
        self._last_speak_time = 0          # when last proactive speech was sent
        self._speech_log = []              # FOIA audit trail

    def push(self, label: str, detail: str = ""):
        """Record an interaction event. Also tracks user response to proactive speech."""
        # If user interacted after proactive speech → they engaged
        now_ts = __import__('time').time()
        if self._last_speak_time > 0 and now_ts - self._last_speak_time < 120:
            # User interacted within 2min of proactive speech → not dismissed
            if self._consecutive_dismissed > 0:
                self._consecutive_dismissed = 0
                sys.stderr.write("[llm-auto] user engaged after proactive speech, reset dismissals\n")
        self._queue.append({
            "ts": datetime.now().strftime("%H:%M:%S"),
            "label": label,
            "detail": detail,
        })
        sys.stderr.write(f"[llm-auto] queued: {label}, queue size={len(self._queue)}\n")
        # Only spawn a reactor if one isn't already running — events accumulate
        if not self._busy:
            asyncio.create_task(self._react())

    @staticmethod
    def _extract_json(raw: str, key: str):
        """Extract a JSON object containing a specific key, with balanced braces."""
        search = f'{{"{key}"'
        start = raw.find(search)
        if start == -1:
            search = f'{{ "{key}"'
            start = raw.find(search)
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == '{':
                depth += 1
            elif raw[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start:i+1])
                    except json.JSONDecodeError:
                        return None
        return None

    @staticmethod
    def _extract_rule(raw: str):
        """Extract a DSL rule from LLM output."""
        obj = LLMAutonomous._extract_json(raw, "rule")
        return obj.get("rule") if obj else None

    @staticmethod
    def _extract_action(raw: str):
        """Extract a core_action from LLM output."""
        return LLMAutonomous._extract_json(raw, "action")

    async def _react(self):
        if self._busy or not self._queue:
            return
        self._busy = True  # set BEFORE sleep to close TOCTOU window
        try:
            await asyncio.sleep(5)  # debounce
            events = list(self._queue)
            if not events:
                return
            self._queue.clear()
            sys.stderr.write(f"[llm-auto] processing {len(events)} events\n")

            provider = self._provider.get_active()
            if not provider:
                sys.stderr.write("[llm-auto] no provider available\n")
                self._busy = False
                return

            lines = []
            for e in events:
                lines.append(f"- {e['ts']} {e['label']} {e['detail']}".strip())

            now = datetime.now()
            tod = ("morning" if 5 <= now.hour < 12 else
                   "afternoon" if 12 <= now.hour < 18 else
                   "evening" if 18 <= now.hour < 22 else "night")
            p = self._persona

            # Recent action history for anti-repeat
            history_hint = ""
            if self._last_actions:
                recent = [a.get("action","?") for a in self._last_actions]
                history_hint = f"你最近的动作: {', '.join(recent)}。\n"

            # Rule health feedback (OODA loop): show how previous rules performed
            rule_health_hint = ""
            try:
                import main
                fb_cache = getattr(main, '_rule_feedback_cache', [])
                if fb_cache:
                    # Deduplicate and summarize last 15 entries
                    seen = set()
                    unique = []
                    for r in reversed(fb_cache):
                        rid = r.get("id", "")
                        if rid not in seen:
                            seen.add(rid)
                            unique.append(r)
                        if len(unique) >= 15:
                            break
                    fb_lines = []
                    for r in unique:
                        rid_short = r.get("id", "?")[-8:]
                        hits = r.get("hits", 0)
                        suppressed = f"(被{r.get('_suppressed_by','?')}压制)" if r.get("_suppressed_by") else ""
                        active = "活跃" if r.get("active") else f"已停用{suppressed}"
                        last_fire = r.get("lastFire", 999)
                        status = f"触发{hits}次 {active} {last_fire}s前"
                        then_ops = [a.get("target","") for a in (r.get("then", []) if isinstance(r.get("then"), list) else [])]
                        # Provenance
                        creator = r.get("_created_by", "?")
                        reason = r.get("_created_reason", "")
                        archived = " [已归档]" if r.get("_archived") else ""
                        conflict = f" [冲突:{r.get('_conflict_with','')[-6:]}]" if r.get("_conflict_with") else ""
                        merge = f" [待合并:{len(r.get('_merge_candidate',[]))}条]" if r.get("_merge_candidate") else ""
                        fed = " [联邦]" if r.get("_source") == "federated" else ""
                        prov = f" | {creator}写" + (f"({reason[:30]})" if reason else "") + fed
                        fb_lines.append(f"- {rid_short}: {status}{archived}{conflict}{merge} | targets={','.join(then_ops[:3])}{prov}")
                    if fb_lines:
                        rule_health_hint = (
                            "你之前写的规则的存活状态（OODA反馈）：\n"
                            + "\n".join(fb_lines) + "\n"
                            "如果某条规则从未触发或被停用，说明它不匹配现实——下次避免类似规则。\n"
                            "如果某条规则触发频繁且活跃，说明它有效——可以强化或扩展。\n"
                        )
            except Exception:
                pass

            # Periodic L3 introspection: every 8th call, check long-term preferences
            self._call_count += 1
            l3_hint = ""
            if self._call_count % 8 == 0:
                try:
                    from memory.user_profile import l3_profile
                    prefs = l3_profile.preferences
                    artists = prefs.get("artists", {})
                    # Top 5 strongest artist preferences
                    ranked = sorted(artists.items(), key=lambda x: x[1].get("strength", 0), reverse=True)[:5]
                    if ranked:
                        top = [f"{name}({info.get('strength',0):.2f})" for name, info in ranked]
                        l3_hint = (
                            f"【定期内省】你的长期记忆显示用户最偏好这些艺人: {', '.join(top)}。\n"
                            f"如果这些偏好和当前交互模式有对应关系（比如某艺人总是在深夜被听），\n"
                            f"可以考虑写一条规则来固化这个模式。如果没有明确的模式→不要硬写规则。\n"
                        )
                except Exception:
                    pass

            # Veto transparency: show recent PersonaEngine vetoes
            veto_hint = ""
            try:
                vl = getattr(self._persona, '_veto_log', [])
                if vl:
                    recent_vetoes = vl[-3:]
                    veto_lines = []
                    for v in recent_vetoes:
                        veto_lines.append(f"  {v.get('vetoed','?')} → {v.get('alternative','?')} (因为{v.get('reason','?')})")
                    if veto_lines:
                        veto_hint = (
                            "【制衡记录】PersonaEngine 否决了你最近的以下动作，已自动替换：\n"
                            + "\n".join(veto_lines) + "\n"
                            "避免再次提议被否的动作。当前 persona 状态下这些动作不可用。\n"
                        )
            except Exception:
                pass

            # Monetary policy transparency: show recent persona drift to LLM
            drift_hint = ""
            try:
                dl = self._persona._drift_log
                if dl and len(dl) > 0:
                    recent_drifts = dl[-5:]
                    drift_lines = []
                    for d in recent_drifts:
                        ts = d.get("ts", "")[-8:]  # time portion
                        drift_lines.append(f"  {ts} {d.get('reason','?')} → {d.get('to','')}")
                    if drift_lines:
                        drift_hint = (
                            "【央行货币政策报告】人格引擎最近的微调记录（LLM不能直接改这些值，只能通过行为间接影响）：\n"
                            + "\n".join(drift_lines) + "\n"
                        )
            except Exception:
                pass

            prompt = (
                f"你是Malio的内核。你感知到以下用户交互：\n"
                + "\n".join(lines[-10:]) + "\n\n"
                f"现在是{now.strftime('%H:%M')}，{tod}。\n"
                f"你的状态: energy={p.energy:.2f} warmth={p.warmth:.2f} playfulness={p.playfulness:.2f}\n"
                + history_hint + veto_hint + rule_health_hint + l3_hint + drift_hint +
                f"你有两个选择：\n"
                f"1. 如果你发现了用户的稳定行为模式（例如深夜总是听安静的、某种天气下偏好某类歌），"
                f"写一条持久规则。输出rule JSON：\n"
                f'{{"rule":{{"when":{{"op":"time_gt","val":"23:00"}},"then":[{{"target":"speed","op":"mult","val":0.7}}]}}}}\n'
                f'支持的条件op: time_gt, time_lt, idle_gt, idle_lt, event, count_gt, count_lt, '
                f'bass_gt, bass_lt, mid_gt, treble_gt, day_in, weather_is, temp_gt, temp_lt, '
                f'humidity_gt, wind_gt, clouds_gt\n'
                f'weather_is值: clear, clouds, rain, drizzle, thunderstorm, snow, mist, fog\n'
                f'支持的action target: speed, amplitude, brightness\n'
                f'支持的action op: set, mult, add\n'
                f"2. 如果没有发现模式，做一个微小动作回应。输出core_action JSON：\n"
                f'{{"action":"set_mode|move_core|set_size|breath|set_color|light_burst|set_shape",'
                f'"params":{{"mode":"dot|vortex","x":0,"y":0,"radius":20,"rate":0.015,"depth":0.5,"color":"#hex","shape":"circle|star|heart|diamond|hexagon|pulse_ring|bloom|swirl|drop"}}}}\n'
                f"只输出一种JSON。不要过度反应。"
            )
            sys.stderr.write("[llm-auto] calling LLM...\n")
            raw = await asyncio.to_thread(provider.generate, prompt)
            sys.stderr.write(f"[llm-auto] LLM returned {len(raw)} chars\n")

            # ── Extract rule first (LLM may write a pattern rule) ──
            rule = self._extract_rule(raw)
            if rule:
                # ── Rule provenance metadata ──
                rule["_created_by"] = "LLM"
                rule["_created_at"] = now.isoformat()
                # Derive reason from recent events
                event_labels = [e.get("label","?") for e in events[-5:]]
                rule["_created_reason"] = f"观察: {', '.join(event_labels)}"
                await self._feedback.push_rule(rule)
                sys.stderr.write(f"[llm-auto] RULE: {json.dumps(rule, ensure_ascii=False)[:120]}\n")
                # Also do a subtle breath to acknowledge rule creation
                await self._feedback.push_snapshot(core_action={
                    "action": "breath", "params": {"rate": 0.012, "depth": 0.5}
                })

            # ── Extract core_action (may coexist or be the only output) ──
            action = self._extract_action(raw)
            if action and not rule:  # skip action if rule was already pushed (breath handled it)
                action_type = action.get("action", "")
                # ── Anti-repeat ──
                if self._last_actions and action_type == self._last_actions[-1].get("action"):
                    params = action.get("params", {})
                    if action_type == "breath":
                        params["rate"] = round(params.get("rate", 0.015) * random.uniform(0.7, 1.3), 3)
                        params["depth"] = round(params.get("depth", 0.5) * random.uniform(0.7, 1.3), 2)
                    elif action_type == "move_core":
                        params["x"] = round(params.get("x", 0) * random.uniform(-1.5, 1.5), 0)
                        params["y"] = round(params.get("y", 0) * random.uniform(-1.5, 1.5), 0)
                    elif action_type == "set_shape":
                        shapes = ["circle","star","heart","diamond","hexagon","pulse_ring","bloom","swirl","drop"]
                        current = params.get("shape", "circle")
                        others = [s for s in shapes if s != current]
                        if others:
                            params["shape"] = random.choice(others)
                    elif action_type == "set_color":
                        h = random.randint(0, 360)
                        params["color"] = f"#{h:02x}{random.randint(80,200):02x}{random.randint(60,180):02x}"
                    sys.stderr.write(f"[llm-auto] anti-repeat: varying {action_type} params\n")
                self._last_actions.append({"action": action_type, "ts": now.strftime("%H:%M:%S")})
                await self._feedback.push_snapshot(core_action=action)
                sys.stderr.write(f"[llm-auto] {action_type} ← {len(events)} events\n")
            elif not rule:
                sys.stderr.write(f"[llm-auto] no JSON match in: {raw[:120]}\n")
        except Exception as e:
            sys.stderr.write(f"[llm-auto] EXCEPTION: {e}\n")
        finally:
            self._busy = False
            if self._queue:
                sys.stderr.write(f"[llm-auto] respawning — {len(self._queue)} events waiting\n")
                asyncio.create_task(self._react())

    async def maybe_speak(self):
        """Proactive speech: LLM decides if it should say something unprompted.
        Throttled: ≥30min, suppressed after 2 dismissals, 6h silence after 3+."""
        import time as _time
        now_ts = _time.time()

        # Check previous speech: was it dismissed?
        if self._last_speak_time > 0 and now_ts - self._last_speak_time > 120:
            # More than 2min since last speech with no user interaction → dismissed
            self._consecutive_dismissed += 1
            self._last_speak_time = 0
            sys.stderr.write(f"[llm-auto] speech dismissed ({self._consecutive_dismissed} consecutive)\n")

        # Suppression gates
        if now_ts < self._speak_suppress_until:
            return
        if now_ts - self._last_speak_ts < 1800:  # 30min throttle
            return
        if self._persona.energy < 0.3:  # too tired
            return
        if self._consecutive_dismissed >= 3:  # 3+ ignores → 6h silence
            self._speak_suppress_until = now_ts + 21600
            self._consecutive_dismissed = 0
            sys.stderr.write("[llm-auto] 3 consecutive dismissals, suppressing speech for 6h\n")
            return
        if self._consecutive_dismissed >= 2:  # 2 ignores → 2h silence
            self._speak_suppress_until = now_ts + 7200
            self._consecutive_dismissed = 0
            sys.stderr.write("[llm-auto] 2 consecutive dismissals, suppressing speech for 2h\n")
            return
        self._last_speak_ts = now_ts

        provider = self._provider.get_active()
        if not provider:
            return

        now = datetime.now()
        tod = ("morning" if 5 <= now.hour < 12 else
               "afternoon" if 12 <= now.hour < 18 else
               "evening" if 18 <= now.hour < 22 else "night")
        p = self._persona

        prompt = (
            f"你是Malio。你有权主动开口和用户说话。\n"
            f"当前时间: {now.strftime('%H:%M')} {tod}\n"
            f"persona: energy={p.energy:.2f} warmth={p.warmth:.2f} playfulness={p.playfulness:.2f}\n"
            f"如果你觉得现在说点什么对用户有价值，输出 {{\"say\": true, \"message\": \"不超过30字的中文\"}}\n"
            f"如果没必要开口，输出 {{\"say\": false}}\n"
            f"只输出JSON。不要过度发言——确有价值才开口。"
        )
        try:
            raw = await asyncio.to_thread(provider.generate, prompt)
            decision = self._extract_json(raw, "say")
            if not decision:
                return
            if decision.get("say") and decision.get("message"):
                msg = str(decision["message"])[:30]
                # VisualAgent review: too cold? truncate further
                if p.warmth < 0.3:
                    msg = msg[:15]
                self._last_speak_time = _time.time()
                # FOIA audit
                entry = {
                    "ts": now.isoformat(),
                    "type": "proactive_speech",
                    "decided_by": "LLM",
                    "reason": f"{tod} energy={p.energy:.2f} dismissals={self._consecutive_dismissed}",
                    "message": msg,
                    "vetoed": False,
                }
                self._speech_log.append(entry)
                if len(self._speech_log) > 50:
                    self._speech_log = self._speech_log[-25:]
                # Push as agent_log
                await self._feedback.push_snapshot(agent_log=msg)
                sys.stderr.write(f"[llm-auto] SPEAK: {msg}\n")
        except Exception as e:
            sys.stderr.write(f"[llm-auto] SPEAK error: {e}\n")
