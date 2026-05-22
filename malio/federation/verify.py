"""Verification script: generate synthetic rules across 3 instances,
embed them, cluster with DBSCAN, and validate grouping quality.

Run: python -m federation.verify
"""

import json
import numpy as np
import os
import sys

# Ensure malio/ is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from federation.embedder import embed_rules, rule_to_sentence, using_sbert
from federation.aggregator import aggregate, _pairwise_dedup, _cosine_sim, estimate_eps
from sklearn.metrics.pairwise import cosine_distances


# ── synthetic rules: 3 instances, intentional semantic groups ───

def _make(when, then, reason="", source="local", hits=0, score=0.5):
    return {
        "id": f"rule_{abs(hash(json.dumps(when)+json.dumps(then)+reason))%10000:04d}",
        "when": when, "then": then,
        "_created_reason": reason, "_source": source,
        "_hits": hits, "_score": score, "_active": True,
    }


def generate():
    """10 rules × 3 instances = 30 rules with 4 semantic clusters."""
    rules = []

    # ── Cluster A: nighttime dimming (6 variants across 3 instances) ──
    rules.append(_make(
        {"op": "time_gt", "val": "23:00"},
        [{"target": "brightness", "op": "mult", "val": 0.5}],
        "用户要求晚上暗一点", "local", 42, 0.85))
    rules.append(_make(
        {"op": "time_gt", "val": "22:00"},
        [{"target": "brightness", "op": "mult", "val": 0.4}],
        "深夜降低亮度", "local", 15, 0.6))
    rules.append(_make(
        {"op": "time_gt", "val": "23:30"},
        [{"target": "brightness", "op": "set", "val": 0.35}],
        "太亮了晚上", "local", 28, 0.72))
    rules.append(_make(
        {"op": "time_gt", "val": "21:00"},
        [{"target": "brightness", "op": "mult", "val": 0.45}],
        "晚上调暗屏幕", "local", 8, 0.5))
    rules.append(_make(
        {"op": "time_gt", "val": "22:30"},
        [{"target": "brightness", "op": "mult", "val": 0.55}],
        "减少夜间亮度", "federated", 3, 0.35))
    rules.append(_make(
        {"op": "time_gt", "val": "23:00"},
        [{"target": "brightness", "op": "mult", "val": 0.6}],
        "晚上暗一点", "federated", 7, 0.28))

    # ── Cluster B: daytime speed boost (4 variants) ──
    rules.append(_make(
        {"op": "time_gt", "val": "08:00"},
        [{"target": "speed", "op": "mult", "val": 1.5}],
        "白天活跃一点", "local", 35, 0.78))
    rules.append(_make(
        {"op": "time_gt", "val": "07:00"},
        [{"target": "speed", "op": "set", "val": 3.0}],
        "早上增加粒子速度", "local", 20, 0.55))
    rules.append(_make(
        {"op": "time_gt", "val": "09:00"},
        [{"target": "speed", "op": "mult", "val": 1.3}],
        "白天加速", "federated", 11, 0.4))
    rules.append(_make(
        {"op": "time_gt", "val": "08:30"},
        [{"target": "speed", "op": "mult", "val": 1.45}],
        "早上活跃点", "local", 17, 0.5))

    # ── Cluster C: rain → warm color (3 variants) ──
    rules.append(_make(
        {"op": "weather_is", "val": "rain"},
        [{"target": "color", "op": "set", "val": "#FF6B35"}],
        "雨天暖色调", "local", 22, 0.7))
    rules.append(_make(
        {"op": "weather_is", "val": "rain,drizzle,thunderstorm"},
        [{"target": "color", "op": "lerp_to", "val": "#FF8C42"}],
        "下雨时让粒子变暖", "local", 14, 0.5))
    rules.append(_make(
        {"op": "weather_is", "val": "rain"},
        [{"target": "color", "op": "set", "val": "#E8734A"}],
        "rain时用暖色", "federated", 6, 0.3))

    # ── Cluster D: idle slowdown (3 variants) ──
    rules.append(_make(
        {"op": "idle_gt", "val": 300},
        [{"target": "speed", "op": "set", "val": 2.0}],
        "空闲5分钟后减速", "local", 50, 0.9))
    rules.append(_make(
        {"op": "idle_gt", "val": 600},
        [{"target": "speed", "op": "mult", "val": 0.7}],
        "10分钟不操作降低速度", "local", 18, 0.6))
    rules.append(_make(
        {"op": "idle_gt", "val": 300},
        [{"target": "speed", "op": "set", "val": 1.8}],
        "无人时减速", "federated", 9, 0.32))

    # ── Noise: unique rules that don't belong to any cluster ──
    rules.append(_make(
        {"op": "event", "val": "song_change"},
        [{"target": "amplitude", "op": "mult", "val": 1.8}],
        "切歌时振幅脉冲", "local", 60, 0.95))
    rules.append(_make(
        {"op": "count_gt", "val": 500},
        [{"target": "density_max", "op": "set", "val": 0.8}],
        "粒子太多时限制密度", "local", 30, 0.75))
    rules.append(_make(
        {"op": "temp_gt", "val": 30},
        [{"target": "color", "op": "set", "val": "#00BFFF"}],
        "高温时冷色调降温", "local", 12, 0.45))
    rules.append(_make(
        {"op": "bass_gt", "val": 0.7},
        [{"target": "amplitude", "op": "mult", "val": 1.5}],
        "重低音增强振幅", "local", 40, 0.82))

    # Assign source labels evenly across 3 "instances"
    for i, r in enumerate(rules):
        if r["_source"] == "local":
            r["_source"] = f"instance_{chr(65 + i % 3)}"  # A, B, C

    return rules


def print_similarity_matrix(rules):
    """Print a compact cosine similarity matrix with labels."""
    vecs = [np.array(v, dtype=np.float64) for v in embed_rules(rules)]
    n = len(rules)
    matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            matrix[i][j] = _cosine_sim(vecs[i], vecs[j])

    # Compact display: show top-3 similarities per rule
    print("\n── Pairwise similarity highlights ──")
    for i, r in enumerate(rules):
        sentence = rule_to_sentence(r)[:70]
        neighbors = sorted(
            [(j, matrix[i][j]) for j in range(n) if j != i],
            key=lambda x: -x[1]
        )[:3]
        print(f"\n  [{r['_source'][-1]}] {sentence}...")
        for j, sim in neighbors:
            print(f"       → {sim:.3f}  [{rules[j]['_source'][-1]}] {rule_to_sentence(rules[j])[:60]}...")


def print_cluster_quality(rules, aggregated, labels, cluster_names):
    """Verify that rules we expect to cluster together actually do."""
    print("\n── Cluster assignment ──")
    for lbl in sorted(set(labels)):
        idx = [i for i, l in enumerate(labels) if l == lbl]
        cluster_rules = [rules[i] for i in idx]
        tag = cluster_names.get(lbl, f"cluster_{lbl}" if lbl >= 0 else "NOISE")
        print(f"\n  [{tag}] {len(cluster_rules)} rules:")
        for r in cluster_rules:
            print(f"    [{r['_source']}] {rule_to_sentence(r)[:80]}")


def main():
    print("=== Federation Verification ===\n")

    # 1) Generate synthetic rules
    rules = generate()
    print(f"Generated {len(rules)} rules across 3 simulated instances")

    # 2) Show each rule as a sentence
    print("\n── Rule → Sentence ──")
    for r in rules:
        print(f"  [{r['_source']}] {rule_to_sentence(r)[:90]}")

    # 3) Embed
    print("\n── Embedding ({n} rules → vectors) ──".format(n=len(rules)))
    vecs = embed_rules(rules)
    print(f"  {len(vecs)} vectors, {len(vecs[0])}d each")

    # 4) Cosine similarity highlights
    print_similarity_matrix(rules)

    # 5) DBSCAN aggregation with auto eps
    print(f"\n── DBSCAN Aggregation (min_samples=2, auto eps) ──")
    print(f"  Embedding backend: {'sentence-transformers' if using_sbert() else 'TF-IDF (lexical)'}")
    vecs_np = np.array([np.array(v, dtype=np.float64) for v in vecs])
    dist_matrix = cosine_distances(vecs_np)
    np.fill_diagonal(dist_matrix, 0.0)
    dist_matrix = np.maximum(dist_matrix, 0.0)
    auto_eps = estimate_eps(dist_matrix, k=2)
    print(f"  Auto-calibrated eps = {auto_eps:.3f}")

    aggregated = aggregate(rules, eps=None, min_samples=2)
    print(f"  {len(rules)} input → {len(aggregated)} output")
    for r in aggregated:
        noise = " [NOISE]" if r.get("_noise") else ""
        size = r.get("_cluster_size", 1)
        ratio = r.get("_federated_ratio", 0)
        print(f"  [{r['_source']}] score={r.get('_score',0):.3f} "
              f"cluster_size={size} fed_ratio={ratio}{noise} "
              f"— {rule_to_sentence(r)[:70]}")

    # 6) Qualitative check
    print("\n── Qualitative check ──")
    clustered_ids = [r["_source"] for r in aggregated if not r.get("_noise")]
    noise_ids = [r["_source"] for r in aggregated if r.get("_noise")]

    # Expected: cluster A (nighttime dimming) should collapse to ~1-2 reps
    # cluster B (daytime speed) → 1-2 reps
    # cluster C (rain warm) → 1 rep
    # cluster D (idle) → 1 rep
    # Noise: song_change, count_gt, temp_gt, bass_gt → 4 individual noise points
    n_clusters = len(set(r.get("_cluster_size", 1) for r in aggregated
                         if not r.get("_noise")))
    print(f"  Clustered groups: {len([r for r in aggregated if not r.get('_noise')])}")
    print(f"  Noise points: {len(noise_ids)}")
    print(f"  Input: {len(rules)}, Output: {len(aggregated)} "
          f"(compression: {len(rules)/len(aggregated):.1f}x)")

    # Sanity: noise should include song_change, count_gt, temp_gt, bass (unique rules)
    noise_sentences = [rule_to_sentence(r) for r in aggregated if r.get("_noise")]
    has_song_change = any("song_change" in s for s in noise_sentences)
    has_count_gt = any("粒子数" in s for s in noise_sentences)
    print(f"  Song change in noise: {has_song_change}")
    print(f"  Particle count guard in noise: {has_count_gt}")

    print("\nDone. Check the output above — similar rules should cluster, unique rules should stay as noise.")


if __name__ == "__main__":
    main()
