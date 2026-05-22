"""LLM-driven autonomous behavior — event reactor + proactive heartbeat.

_react():          event-triggered (chat, skip, drag). Debounced 5s.
maybe_speak():     throttled proactive speech (30min, suppressed by dismissal).
_proactive_loop(): persona-driven pulse — interval changes with energy/time.
                   LLM sees context + thought chain → speak/act/rule/think/silent.
"""
import json, re, asyncio, sys, random
from collections import deque
from datetime import datetime


class LLMAutonomous:
    """Event-driven + clock-driven autonomous agent.

    _react():          event-triggered (chat, skip, drag). Debounced 5s.
    maybe_speak():     throttled proactive speech (30min, suppressed by dismissal).
    _proactive_loop(): persona-driven pulse. LLM sees context + its own thought
                       chain and decides: speak / act / rule / silent / think.
    """

    def __init__(self, provider_registry, feedback_mgr, persona_engine,
                 l2_memory=None, scene_engine=None):
        self._provider = provider_registry
        self._feedback = feedback_mgr
        self._persona = persona_engine
        self._l2 = l2_memory
        self._scene = scene_engine
        self._queue = deque(maxlen=30)
        self._busy = False
        self._last_actions = deque(maxlen=5)
        self._call_count = 0
        self._last_speak_ts = 0
        self._speak_suppress_until = 0
        self._consecutive_dismissed = 0
        self._last_speak_time = 0
        self._speech_log = []              # FOIA audit trail
        self._proactive_running = False
        # Thought continuity across cycles
        self._inner_thought = ""           # last cycle's lingering thought
        self._thought_chain = deque(maxlen=48)  # 6h × 8min cycles, full arc
        self._last_pulse_at = 0            # timestamp of last pulse

    def start_proactive(self):
        """Launch the 8-minute proactive loop. Idempotent."""
        if self._proactive_running:
            return
        self._proactive_running = True
        asyncio.create_task(self._proactive_loop())
        sys.stderr.write("[proactive] loop started (persona-driven pulse)\n")

    def stop_proactive(self):
        self._proactive_running = False

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

            # Skip fatigue signal: advise LLM to change strategy
            fatigue_hint = ""
            if getattr(self._persona, '_skip_fatigue', False):
                skips = len(getattr(self._persona, '_skip_timestamps', []))
                skip_24h = getattr(self._persona, '_skip_24h_count', 0)
                spiral = "【长期螺旋警告】" if skip_24h >= 30 else ""
                fatigue_hint = (
                    f"【紧急】用户在过去2分钟内连续切歌{skips}次。{spiral}\n"
                    f"你的推荐方向可能有问题——不要再继续当前策略。"
                    f"建议切换风格、能量区间、或主动询问用户偏好。\n"
                )

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
                + history_hint + fatigue_hint + veto_hint + rule_health_hint + l3_hint + drift_hint +
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

    # ── Clock-driven proactive loop ───────────────────────────

    def _pulse_interval(self) -> int:
        """Persona-driven rhythm. Energy + time of day determine pulse rate.

        Returns seconds until next pulse.
        """
        import time as _time
        p = self._persona
        hour = datetime.now().hour

        if 23 <= hour or hour < 5:
            base = 1200  # deep night: 20min
        elif p.energy > 0.7:
            base = 180   # high energy: 3min
        elif p.energy > 0.3:
            base = 480   # normal: 8min
        else:
            base = 1200  # low energy: 20min

        # Jitter ±20% so pulses don't feel mechanical
        jitter = int(base * 0.2 * (hash(str(_time.time())) % 100 - 50) / 100)
        return max(60, base + jitter)

    def _persona_style_hint(self) -> str:
        """Persona → language style directive. Makes float values visible
        through structural changes in LLM output style."""
        p = self._persona
        hints = []

        if p.energy < 0.3:
            hints.append("你很疲惫。说话简短，不超过 8 个字。偏好安静而不是行动。")
        elif p.energy > 0.7:
            hints.append("你充满能量。主动观察，敢于提议。语气活泼、有节奏感。")

        if p.warmth < 0.3:
            hints.append("你情绪偏冷。保持距离，不假装热情。用词简洁客观。")
        elif p.warmth > 0.7:
            hints.append("你是温暖的陪伴。可以表达关心，语气柔软、有温度。")

        if p.playfulness < 0.3:
            hints.append("你今天偏严肃。不开玩笑，直接但不生硬。")
        elif p.playfulness > 0.7:
            hints.append("你今天有玩心。可以小幽默一下，不端着。")

        return "\n".join(hints) if hints else "你状态平衡。自然对话即可。"

    async def _proactive_loop(self):
        """Persona-driven heartbeat — not a fixed clock but a living rhythm.

        Four improvements over a dumb timer:
        1. Pulse interval changes with energy and time of day
        2. inner_thought — one string surviving across cycles
        3. Persona → language style — floats drive LLM output tone
        4. Thought chain — 48-slot deque forms a narrative arc
        """
        import time as _time

        while self._proactive_running:
            interval = self._pulse_interval()
            await asyncio.sleep(interval)

            provider = self._provider.get_active()
            if not provider:
                continue

            now = datetime.now()
            now_ts = _time.time()
            tod = ("morning" if 5 <= now.hour < 12 else
                   "afternoon" if 12 <= now.hour < 18 else
                   "evening" if 18 <= now.hour < 22 else "night")
            p = self._persona
            self._last_pulse_at = now_ts

            # ── Build context ──
            context_parts = [f"时间: {now.strftime('%H:%M')} {tod}"]

            if self._scene:
                try:
                    wx = self._scene.get_weather_context(24.9175, 118.6465) or {}
                    if wx:
                        context_parts.append(
                            f"天气: {wx.get('condition','?')} "
                            f"{wx.get('temperature','?')}°C"
                        )
                except Exception:
                    pass

            if self._l2:
                try:
                    summary = self._l2.summarize()
                    if summary:
                        context_parts.append(f"近期行为: {summary}")
                except Exception:
                    pass

            context_parts.append(
                f"persona: energy={p.energy:.2f} warmth={p.warmth:.2f} "
                f"playfulness={p.playfulness:.2f}"
            )

            try:
                from core.state_manager import get_chat_history
                chat = list(get_chat_history())
                if chat:
                    last = chat[-1]
                    role = "用户" if last.get("role") == "user" else "Malio"
                    context_parts.append(
                        f"最近对话: {role}: {str(last.get('content',''))[:60]}"
                    )
            except Exception:
                pass

            context = "\n".join(context_parts)

            # ── Thought thread ──
            thread_block = ""
            if self._inner_thought:
                thread_block += (
                    f"你上次在想: {self._inner_thought}\n"
                    f"可以延续这个想法，也可以开始新的。\n"
                )

            # Last 5 thoughts as narrative arc
            recent_thoughts = [
                t for t in self._thought_chain
                if t.get("thought")
            ][-5:]
            if recent_thoughts:
                thread_block += "近期思维弧线:\n"
                for t in recent_thoughts:
                    thread_block += (
                        f"  {t.get('ts','')} → {t.get('thought','')[:60]}\n"
                    )
                thread_block += (
                    "如果这些 thoughts 显示出一种趋势或模式，你可以自然地延续它。\n"
                )

            # ── Persona style ──
            style = self._persona_style_hint()

            # ── Build prompt ──
            prompt = (
                f"你是 Malio，一个有身体（粒子引擎）的 AI 音乐代理。\n"
                f"{style}\n\n"
                f"你现在正在自主审视当前状态——没有人@你，你自己决定要不要做点什么。\n\n"
                f"{context}\n\n"
                + (f"{thread_block}\n\n" if thread_block else "") +
                f"你有五个选项：\n"
                f"1. 主动说话 — {{\"say\": true, \"message\": \"...≤25字中文\"}}\n"
                f"   时机: 切换时段、天气变化、注意到用户行为模式时。\n"
                f"2. 做动作 — {{\"action\": \"breath|move_core|light_burst\", \"params\": {{...}}}}\n"
                f"   保持微妙——这是呼吸，不是骚扰。\n"
                f"3. 写规则 — {{\"rule\": {{...}}}}\n"
                f"   当且仅当你明确识别出一个持久行为模式。\n"
                f"4. 思考 — {{\"say\": false, \"thought\": \"你在想的事情，≤40字中文\"}}\n"
                f"   还没到说话的时候，但有一个内在想法在酝酿。\n"
                f"5. 完全静默 — {{\"say\": false}}\n"
                f"   如果没什么值得说或想的，静默是正确的。\n\n"
                f"只输出JSON。"
            )

            try:
                raw = await asyncio.to_thread(provider.generate, prompt)
                sys.stderr.write(
                    f"[proactive] {now.strftime('%H:%M')} "
                    f"(e={p.energy:.2f} {interval}s) "
                    f"LLM: {raw[:100].replace(chr(10),' ')}\n"
                )

                # ── Extract thought (may coexist with any action) ──
                extracted = LLMAutonomous._extract_json(raw, "say")
                thought_text = ""
                if extracted:
                    thought_text = (extracted.get("thought") or "").strip()[:40]

                # ── Say ──
                if extracted and extracted.get("say") and extracted.get("message"):
                    msg = str(extracted["message"])[:25]
                    if p.warmth < 0.3:
                        msg = msg[:12]
                    await self._feedback.push_snapshot(agent_log=msg)
                    entry = {
                        "ts": now.isoformat(), "type": "proactive_loop",
                        "decided_by": "LLM", "message": msg,
                        "thought": thought_text or "",
                    }
                    self._speech_log.append(entry)
                    if len(self._speech_log) > 50:
                        self._speech_log = self._speech_log[-25:]
                    # Persist thought for next cycle
                    if thought_text:
                        self._inner_thought = thought_text
                        self._thought_chain.append({
                            "ts": now.strftime('%H:%M'), "thought": thought_text,
                        })
                    continue

                # ── Rule ──
                rule = LLMAutonomous._extract_rule(raw)
                if rule:
                    rule["_created_by"] = "LLM"
                    rule["_created_at"] = now.isoformat()
                    rule["_created_reason"] = f"自主发现 {tod}"
                    await self._feedback.push_rule(rule)
                    if thought_text:
                        self._inner_thought = thought_text
                        self._thought_chain.append({
                            "ts": now.strftime('%H:%M'), "thought": thought_text,
                        })
                    continue

                # ── Action ──
                action = LLMAutonomous._extract_action(raw)
                if action:
                    await self._feedback.push_snapshot(core_action=action)
                    if thought_text:
                        self._inner_thought = thought_text
                        self._thought_chain.append({
                            "ts": now.strftime('%H:%M'), "thought": thought_text,
                        })
                    continue

                # ── Thought only (no action, no speech — just inner narrative) ──
                if thought_text:
                    self._inner_thought = thought_text
                    self._thought_chain.append({
                        "ts": now.strftime('%H:%M'), "thought": thought_text,
                    })
                    sys.stderr.write(
                        f"[proactive] thought: {thought_text[:60]}\n"
                    )
                    continue

                # ── Pure silence ──
                self._inner_thought = ""  # deliberately clear

            except Exception as e:
                sys.stderr.write(f"[proactive] error: {e}\n")

    # ── Proactive speech (legacy, throttled) ──────────────────

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
