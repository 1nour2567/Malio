"""FederationSync — periodic peer pull for cross-instance rule sharing.

Default interval: 3600s (1h). Set FEDERATION_PEERS in .env to a
comma-separated list of peer URLs. Empty list disables sync.

Trust model: peers are assumed to be the same user's other devices.
No authentication, no encryption — Malio's threat model is single-user,
not multi-tenant.
"""

import asyncio
import httpx

_SYNC_INTERVAL = 3600  # 1 hour between sync cycles


class FederationSync:
    def __init__(self, peers: list[str], interval: int = _SYNC_INTERVAL):
        self._peers = [p.rstrip("/") for p in peers if p.strip()]
        self._interval = interval
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def active(self) -> bool:
        return len(self._peers) > 0

    async def start(self):
        if not self.active:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        while self._running:
            await asyncio.sleep(self._interval)
            await self._sync_cycle()

    async def _sync_cycle(self):
        from core.state_manager import get_agent_rules, state_store
        from .embedder import embed_single
        from .aggregator import is_semantic_duplicate, aggregate, evolve_trust

        local_rules = list(get_agent_rules())
        local_vecs = [embed_single(r) for r in local_rules] if local_rules else []

        total_imported = 0
        total_dupes = 0

        async with httpx.AsyncClient(timeout=15.0) as client:
            for peer in self._peers:
                try:
                    resp = await client.get(f"{peer}/api/rules/export")
                    resp.raise_for_status()
                    foreign = resp.json().get("rules", [])
                except Exception:
                    continue  # peer down — skip, try next cycle

                for r in foreign:
                    # Skip system rules
                    if r.get("id", "").startswith("sys_"):
                        continue

                    if local_vecs and is_semantic_duplicate(r, local_vecs, threshold=0.85):
                        total_dupes += 1
                        continue

                    r["_source"] = "federated"
                    r["_imported_at_isostr"] = resp.headers.get("date", "")
                    import time as _time
                    r["_imported_at_ts"] = int(_time.time())
                    r["_score"] = round((r.get("_score", 0.5) or 0.5) * 0.7, 3)
                    r["_active"] = True
                    local_rules.append(r)
                    local_vecs.append(embed_single(r))
                    total_imported += 1

        if total_imported > 0:
            aggregated = aggregate(local_rules, min_samples=2)
            evolve_trust(aggregated)
            s = get_agent_rules()
            s.clear()
            s.extend(aggregated)
            state_store.mark_dirty("default")
