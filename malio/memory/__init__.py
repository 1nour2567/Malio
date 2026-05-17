"""Malio Memory System — L1-L4 architecture.
L1: instant (Reasoner context, 5-10 exchanges)
L2: short-term (24h behavior snapshots)
L3: long-term (dynamic user profile, updateable)
L4: permanent (immutable fact log, append-only)
"""
from .short_term import L2Memory, l2_memory
from .user_profile import L3Profile, l3_profile
from .history import L4History, l4_history

__all__ = ["L2Memory", "L3Profile", "L4History", "l2_memory", "l3_profile", "l4_history"]
