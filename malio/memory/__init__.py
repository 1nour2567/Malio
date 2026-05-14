"""Malio Memory System — L1-L4 architecture.
L1: instant (Reasoner context, 5-10 exchanges)
L2: short-term (24h behavior snapshots)
L3: long-term (dynamic user profile, updateable)
L4: permanent (immutable fact log, append-only)
"""
from .short_term import L2Memory
from .user_profile import L3Profile

__all__ = ["L2Memory", "L3Profile"]
