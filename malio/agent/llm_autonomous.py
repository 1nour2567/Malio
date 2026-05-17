"""LLM-driven autonomous behavior — context-aware core actions.

Triggered after user interactions (chat, skip).  Debounced 5s.
LLM sees event summary + persona state + time → outputs one core_action.
"""
import json, re, asyncio, sys
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

    def push(self, label: str, detail: str = ""):
        """Record an interaction event. Call this from chat/WS handlers."""
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
    def _extract_action(raw: str):
        """Extract JSON with balanced braces, handling nested params."""
        start = raw.find('{"action"')
        if start == -1:
            start = raw.find('{ "action"')
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

            prompt = (
                f"你是Malio的内核。你感知到以下用户交互：\n"
                + "\n".join(lines[-10:]) + "\n\n"
                f"现在是{now.strftime('%H:%M')}，{tod}。\n"
                f"你的状态: energy={p.energy:.2f} warmth={p.warmth:.2f} playfulness={p.playfulness:.2f}\n"
                f"请做一个有意义的微小动作回应这些交互。输出core_action JSON（仅JSON）:\n"
                f'{{"action":"set_mode|move_core|set_size|breath|set_color|light_burst|set_shape",'
                f'"params":{{"mode":"dot|vortex","x":0,"y":0,"radius":20,"rate":0.015,"depth":0.5,"color":"#hex","shape":"circle|star|heart|diamond|hexagon|pulse_ring|bloom|swirl|drop"}}}}\n'
                f"不要过度反应——只做一件事。"
            )
            sys.stderr.write("[llm-auto] calling LLM...\n")
            raw = await asyncio.to_thread(provider.generate, prompt)
            sys.stderr.write(f"[llm-auto] LLM returned {len(raw)} chars\n")
            action = self._extract_action(raw)
            if action:
                await self._feedback.push_snapshot(core_action=action)
                sys.stderr.write(f"[llm-auto] {action.get('action','?')} ← {len(events)} events\n")
            else:
                sys.stderr.write(f"[llm-auto] no JSON match in: {raw[:120]}\n")
        except Exception as e:
            sys.stderr.write(f"[llm-auto] EXCEPTION: {e}\n")
        finally:
            self._busy = False
