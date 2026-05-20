<p align="center">
  <img src="https://img.shields.io/badge/status-active-success?style=for-the-badge" alt="Status">
  <img src="https://img.shields.io/badge/tests-75%20passed-brightgreen?style=for-the-badge" alt="Tests">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/IUI-2027%20Demo-ff69b4?style=for-the-badge" alt="IUI 2027">
</p>

<h1 align="center">🎵 Malio</h1>
<h3 align="center">An Embodied Music AI with Constitutional Agent Architecture</h3>

<p align="center">
  <b>800 particles · 9-shape morphable core · beat-synchronized pulse · water ripple physics</b>
</p>

<br>

> **Paper** — IUI 2027 Demo: *"Malio: An Embodied Music AI with Constitutional Agent Architecture"*

---

## ✨ What is Malio?

Malio is not a chatbot. It's an **embodied AI music agent** with a physical presence — 800 particles forming a morphable 9-shape core that pulses to the beat, ripples like water, and moves autonomously. It **collects music by spatial gesture** (drag the core over song particles), not by clicking buttons.

Its multi-agent system enforces **jurisdiction boundaries in code** — not through prompt engineering, but through a constitutional separation of powers that no single agent can violate.

---

## 🏛 Architecture

```
                         ┌───────────────────────────┐
                         │     PersonaEngine         │
                         │   (Central Bank)          │
                         │   energy · warmth · play  │
                         │   Phillips Curve tradeoff │
                         └────────────┬──────────────┘
                                      │ constraints
User Input ──► Pipeline (5-stage) ──► Multi-Agent Federation
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
        MusicAgent               VisualAgent             LLM Autonomous
        (ReAct loop)             (rule engine)           (event-driven)
        music search             60fps DSL exec          proactive speech
```

### Three-Tier Rule Governance

```
  ┌────────────┐      ┌──────────────────┐      ┌──────────────┐
  │  T1: LLM   │ ───► │  T2: Rule Engine │ ───► │ T3: Executor │
  │  Observer  │      │  eval + persona  │      │  60fps DSL   │
  │  ~1×/obs   │      │  (zero LLM)      │      │  (client)    │
  └────────────┘      └──────────────────┘      └──────────────┘
   writes rules         manages lifecycle        every frame
```

| Layer | Role | Cost |
|-------|------|------|
| **L2** | Short-term memory (24h window) | RAM |
| **L3** | User profile (text2vec 768d) | Disk |
| **L4** | Audit log (SHA256, append-only) | Disk |

**Output**: 800 Particles + 9-Shape Morphable Core @ Canvas 2D 60fps

---

## 🔥 Key Innovations

<table>
<tr>
<td width="50%">

### 1. Three-Tier Rule Governance

LLM writes rules **once**, they run for **hours** at zero inference cost. Separates authorship (LLM), lifecycle management (rule engine), and frame-level execution (DSL). Reusable for any embodied AI.

</td>
<td width="50%">

### 2. Constitutional Agent Architecture

Separation of powers **enforced in code**: legislative (LLM writes rules), executive (VisualAgent manages), judicial (PersonaEngine constraints), central bank (independent personality policy).

</td>
</tr>
<tr>
<td>

### 3. Structural Personality Constraints

Persona boundaries are **code-level clamps**, not prompt text.  
`energy < 0.3 → block light_burst` — the LLM **cannot** emit blocked actions.  
✅ 10 jailbreak attacks · Δenergy = 0.000

</td>
<td>

### 4. Spatial Nebula Capture

Collect music by **physically dragging** the core over song particles in the agent's body space. Embodied gesture replaces abstract UI buttons.

</td>
</tr>
</table>

---

## 🚀 Quick Start

### Backend

```bash
cd malio
pip install -r requirements.txt
cp .env.example .env   # add your API keys
python main.py          # → http://localhost:8007
```

### Frontend

```bash
cd frontend
npm install
npm run dev             # → http://localhost:5173
```

### Requirements

| Dependency | Version |
|-----------|---------|
| Python | 3.11+ |
| FastAPI + httpx + Pydantic + SQLAlchemy + Pydub | latest |
| Node.js | 18+ (Vite) |
| DeepSeek or Kimi API key | — |
| NetEase Cloud Music API | optional |

---

## ⚙️ Configuration

```env
# LLM Provider (DeepSeek primary, Kimi fallback)
DEEPSEEK_API_KEY=sk-...
KIMI_API_KEY=sk-...

# Optional integrations
SPOTIFY_CLIENT_ID=
OPENWEATHER_API_KEY=
NETEASE_API_URL=http://localhost:3000
```

---

## 🧪 Test Suite

<p align="center">
  <b>75 tests · 0 failures · 100% pass rate</b>
</p>

| Category | Tests | Status |
|----------|:-----:|:------:|
| Smoke tests (httpx + ASGI) | 16 | ✅ |
| PersonaEngine stress | 24 | ✅ |
| Skip fatigue precision | 25 | ✅ |
| Jailbreak immunity | 10 | ✅ |

```bash
cd malio
python -m pytest tests/test_smoke.py -v
python tests/test_persona_stress.py
python tests/test_skip_fatigue.py
python tests/test_jailbreak_stress.py
```

---

## 📁 Project Structure

<details>
<summary><b>malio/</b> — Backend (click to expand)</summary>

```
malio/
├── main.py                      FastAPI entry point
├── agent/
│   ├── pipeline.py              5-stage chat pipeline
│   ├── reasoner.py              LLM prompt + JSON output enforcement
│   ├── router.py                Intent classification + cross-jurisdiction guard
│   ├── persona.py               PersonaEngine (central bank)
│   ├── llm_autonomous.py        Event-driven autonomous behavior
│   ├── visual_agent.py          Rule engine, color blend, rule management
│   └── music_agent.py           Independent ReAct music agent
├── core/
│   ├── state_manager.py         Per-user state + atomic file persistence
│   └── audio_analyzer.py        FFT-based E/W/D extraction
├── memory/
│   ├── short_term.py            L2 memory (24h)
│   ├── user_profile.py          L3 profile (text2vec 768d)
│   └── history.py               L4 append-only audit log
└── tests/
    ├── test_smoke.py            16 smoke tests
    ├── test_persona_stress.py   24 stress tests
    ├── test_skip_fatigue.py     25 precision tests
    └── test_jailbreak_stress.py 10 jailbreak tests
```
</details>

<details>
<summary><b>frontend/src/</b> — Frontend (click to expand)</summary>

```
frontend/src/
├── app.js                       Application controller
├── particles.js                 Particle engine (800 particles, 9 shapes)
├── particle-rules.js            DSL rule executor (60fps)
├── audio-analyzer.js            Web Audio API beat detection
└── ws-client.js                 WebSocket client
```
</details>

---

## ⚠️ Known Limitations

| Limitation | Status |
|-----------|--------|
| 5-minute T2 rule review window | Accepted (speed vs safety tradeoff) |
| MusicAgent → VisualAgent indirect causation via E/W/D | Known design tension |
| Rule explosion (50+ rules × 60fps) | Not yet benchmarked |

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <sub>Built with ❤️ for IUI 2027</sub>
</p>
