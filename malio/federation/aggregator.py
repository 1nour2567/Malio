"""DBSCAN clustering + medoid selection for federated rule aggregation.

Does NOT average rules. Instead:
  1. Embed all rules → vectors
  2. DBSCAN groups semantically similar rules into clusters
  3. Pick medoid (most central rule) per cluster as the representative
  4. Score-down federated rules (×0.7), archive noise points
"""

import math
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import cosine_distances

from .embedder import embed_rules, rule_to_sentence


def _cosine_sim(a, b):
    """1 - cosine distance. Returns float in [-1, 1]."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    a_norm = a / (np.linalg.norm(a) + 1e-12)
    b_norm = b / (np.linalg.norm(b) + 1e-12)
    return float(np.dot(a_norm, b_norm))


def _medoid_of(vectors: np.ndarray, rules: list[dict]) -> dict:
    """Pick the rule whose vector has the smallest mean cosine distance to
    every other vector in the same cluster. This is the 'most central' rule."""
    if len(rules) == 1:
        return rules[0]

    dists = cosine_distances(vectors)
    # Sum of distances to every other point in the cluster
    total_dists = dists.sum(axis=1)
    best_idx = int(np.argmin(total_dists))
    return rules[best_idx]


def estimate_eps(dist_matrix: np.ndarray, k: int = 2) -> float:
    """Auto-calibrate eps from the k-distance elbow.

    Sorts k-NN distances across all points, picks the value at the sharpest
    curvature (elbow). For small datasets (<10 points), uses a fixed heuristic
    because the elbow method is unreliable with few samples.
    """
    n = dist_matrix.shape[0]
    if n <= k + 1:
        return 0.30  # not enough data for clustering

    # k-th nearest neighbor distance for each point (excluding self)
    k_dists = np.sort(dist_matrix, axis=1)[:, k]
    k_dists.sort()

    if n < 10:
        # Small dataset: use the 70th percentile of k-distances.
        # Conservative — forms fewer, tighter clusters to avoid false grouping.
        eps = float(np.percentile(k_dists, 70))
    else:
        # Elbow: point of maximum curvature via second derivative
        dx = np.arange(len(k_dists))
        d2 = np.gradient(np.gradient(k_dists, dx), dx)
        elbow_idx = int(np.argmax(np.abs(d2)))
        eps = float(k_dists[elbow_idx])

    # Clamp to reasonable range for cosine distance
    eps = max(0.10, min(0.85, eps))
    return round(eps, 3)


def aggregate(rules: list[dict],
              eps: float = None,
              min_samples: int = 2,
              federated_score_mult: float = 0.7) -> list[dict]:
    """Aggregate cross-instance rules via DBSCAN clustering.

    Args:
        rules: All rules from all instances (must have _source field).
        eps: DBSCAN epsilon in cosine-distance space. 0.20 ≈ "same meaning
             in different words" for multilingual-MiniLM. Calibrate with
             k-distance plot on real data.
        min_samples: Minimum rules to form a cluster.
        federated_score_mult: Score multiplier applied to federated rules
             on top of any existing score-down.

    Returns:
        Aggregated rule list (one representative per cluster, plus noise).
    """
    if len(rules) < 3:
        return _pairwise_dedup(rules)

    if len(rules) < 10:
        # Small dataset: DBSCAN unstable. Use pairwise dedup with tight
        # threshold, then keep noise points from the loose pass.
        return _pairwise_dedup(rules, threshold=0.85)

    # 1) Embed all rules
    vectors = np.array(embed_rules(rules), dtype=np.float64)

    # 2) DBSCAN in cosine-distance space
    dist_matrix = cosine_distances(vectors)
    # Fix tiny negative values from floating-point noise
    np.fill_diagonal(dist_matrix, 0.0)
    dist_matrix = np.maximum(dist_matrix, 0.0)

    # Auto-calibrate eps if not provided
    if eps is None:
        eps = estimate_eps(dist_matrix, k=min_samples)
    print(f"[aggregator] eps={eps:.3f} (auto)" if eps else f"[aggregator] eps={eps}")

    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric="precomputed")
    labels = clustering.fit_predict(dist_matrix)

    # 3) Per cluster: pick medoid, score-down federated rules
    aggregated = []
    unique_labels = set(labels)

    for lbl in sorted(unique_labels):
        idx = np.where(labels == lbl)[0]
        cluster_vecs = vectors[idx]
        cluster_rules = [rules[i] for i in idx]

        if lbl == -1:
            # Noise points — archive all with low score
            for r in cluster_rules:
                r["_score"] = round((r.get("_score", 0.5) or 0.5) * 0.3, 3)
                r["_noise"] = True
                aggregated.append(r)
        else:
            representative = _medoid_of(cluster_vecs, cluster_rules)
            rep = dict(representative)  # shallow copy

            # Count federated vs local sources in this cluster
            federated_count = sum(
                1 for r in cluster_rules
                if r.get("_source") == "federated"
            )
            n = len(cluster_rules)
            rep["_cluster_size"] = n
            rep["_federated_ratio"] = round(federated_count / n, 2)

            # Score: weighted blend of medoid's own score × federation penalty
            base_score = rep.get("_score", 0.5) or 0.5
            if rep.get("_source") == "federated":
                base_score *= federated_score_mult
            rep["_score"] = round(base_score, 3)
            rep["_source"] = rep.get("_source", "federated")

            aggregated.append(rep)

    return aggregated


def _pairwise_dedup(rules: list[dict], threshold: float = 0.85) -> list[dict]:
    """Fallback: greedy pairwise dedup when there aren't enough rules for DBSCAN."""
    if len(rules) <= 1:
        return rules

    vectors = [np.array(v, dtype=np.float64) for v in embed_rules(rules)]
    kept = []
    kept_vecs = []

    for i, r in enumerate(rules):
        is_dup = False
        for j, kv in enumerate(kept_vecs):
            sim = _cosine_sim(vectors[i], kv)
            if sim > threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(r)
            kept_vecs.append(vectors[i])

    for r in kept:
        if r.get("_source") == "federated":
            r["_score"] = round((r.get("_score", 0.5) or 0.5) * 0.7, 3)

    return kept


def is_semantic_duplicate(rule: dict,
                          existing_vectors: list[np.ndarray],
                          threshold: float = 0.85) -> bool:
    """Check if a rule semantically duplicates any existing rule.

    Drop-in replacement for the current json.dumps(when) exact match in
    the import endpoint.
    """
    if not existing_vectors:
        return False
    new_vec = np.array(embed_rules([rule])[0], dtype=np.float64)
    for ev in existing_vectors:
        if _cosine_sim(new_vec, ev) > threshold:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════
# Trust evolution — federated rules earn their place over time
# ═══════════════════════════════════════════════════════════════════

# Days a federated rule must survive before trust evaluation
OBSERVATION_DAYS = 7
# Hits threshold to promote from observed → trusted
PROMOTION_HITS = 10


def evolve_trust(rules: list[dict],
                 now_ts: float = None) -> list[dict]:
    """Promote or archive federated rules based on real-world performance.

    State machine:
        imported (×0.7) ──7d, hits≥10──▶ trusted (score restored)
        imported (×0.7) ──7d, hits=0 ──▶ archived (_active=False)
        imported (×0.7) ──7d, 1-9 hits ─▶ stays observed (keep ×0.7)

    Local rules and already-promoted rules are untouched.

    Args:
        rules: Full rule list. Modified in-place, also returned.
        now_ts: Current unix timestamp. Defaults to time.time().

    Returns:
        Same list with trust states mutated.
    """
    import time as _time
    if now_ts is None:
        now_ts = _time.time()

    for r in rules:
        if r.get("_source") != "federated":
            continue
        if r.get("_trust") == "promoted":
            continue  # already trusted, don't re-evaluate

        imported_at = r.get("_imported_at_ts", 0)
        if not imported_at:
            # No timestamp — set one now as baseline
            r["_imported_at_ts"] = int(now_ts)
            continue

        age_days = (now_ts - imported_at) / 86400
        if age_days < OBSERVATION_DAYS:
            continue  # still in observation window

        hits = r.get("_hits", 0)

        if hits >= PROMOTION_HITS:
            # Restore full score (undo the ×0.7 import penalty)
            current_score = r.get("_score", 0.35) or 0.35
            r["_score"] = round(min(1.0, current_score / 0.7), 3)
            r["_trust"] = "promoted"
        elif hits == 0:
            r["_active"] = False
            r["_score"] = round((r.get("_score", 0.35) or 0.35) * 0.1, 3)
            r["_trust"] = "archived"
        # else: 1-9 hits → stay in observation, _trust stays None

    return rules
