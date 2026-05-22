"""Rule → natural language sentence → embedding vector.

Production path: sentence-transformers (semantic, requires PyTorch)
Fallback path: TfidfVectorizer (lexical, lightweight, sklearn-only)

Both output vectors that the aggregator can cluster. Swap MODEL_NAME
and remove the fallback when PyTorch is available.
"""

import os
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# HuggingFace is blocked in some regions. hf-mirror.com is a community mirror.
# Set before any other HF import so hub downloads route through the mirror.
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

_USE_SBERT = False
_model = None
_tfidf = None

try:
    from sentence_transformers import SentenceTransformer
    _USE_SBERT = True
except ImportError:
    _tfidf = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        max_features=768,
    )


def describe_conditions(when: dict) -> str:
    """Convert a DSL 'when' block to Chinese natural language."""
    if not when:
        return "任何时候"

    op = when.get("op") or when.get("type", "")
    val = when.get("val", "")

    parts = {
        "time_gt": f"在{val}之后",
        "time_lt": f"在{val}之前",
        "idle_gt": f"当用户空闲超过{val}秒时",
        "event": f"当发生{val}事件时",
        "always": "始终",
        "count_gt": f"当粒子数超过{val}时",
        "count_lt": f"当粒子数少于{val}时",
        "weather_is": f"当天气为{val}时",
        "temp_gt": f"当温度超过{val}度时",
        "temp_lt": f"当温度低于{val}度时",
        "day_in": f"在{val}这些天",
        "bass_gt": f"当低音超过{val}时",
    }
    return parts.get(op, f"条件{op}={val}")


def describe_actions(then: list) -> str:
    """Convert DSL 'then' actions to Chinese natural language."""
    if not then:
        return "不改变任何参数"

    target_names = {
        "speed": "粒子速度", "brightness": "亮度",
        "amplitude": "振幅", "density": "密度",
        "color": "颜色", "density_max": "密度上限",
        "genre_boost": "推荐流派权重", "genre_suppress": "降低流派权重",
        "energy_bias": "能量偏好", "novelty_bias": "新鲜度偏好",
        "language_bias": "语言偏好",
    }
    op_names = {"set": "设为", "mult": "乘以", "add": "增加",
                "lerp_to": "渐变到", "clamp": "限制在",
                "boost": "提升", "suppress": "降低", "bias": "偏向"}

    clauses = []
    for a in then:
        target = target_names.get(a.get("target", ""), a.get("target", "参数"))
        op = op_names.get(a.get("op", ""), a.get("op", "修改为"))
        val = a.get("val", "")
        if isinstance(val, float):
            val = f"{val:.0%}" if 0 < val <= 1 else f"{val:.2f}"
        clauses.append(f"将{target}{op}{val}")

    return "，".join(clauses)


def rule_to_sentence(rule: dict) -> str:
    """Serialize a DSL rule into one Chinese sentence for embedding."""
    when = describe_conditions(rule.get("when", {}))
    then = describe_actions(rule.get("then", []))
    reason = rule.get("_created_reason") or rule.get("note") or ""

    sentence = f"{when}时，{then}。"
    if reason:
        sentence += f" 创建原因：{reason}"
    return sentence


def embed_rules(rules: list[dict]) -> list[list[float]]:
    """Embed a list of rules into vectors."""
    sentences = [rule_to_sentence(r) for r in rules]

    if _USE_SBERT:
        global _model
        if _model is None:
            _model = SentenceTransformer(MODEL_NAME)
        embeddings = _model.encode(sentences, show_progress_bar=False)
        return [e.tolist() for e in embeddings]
    else:
        # TF-IDF fallback: fit on current batch, transform
        global _tfidf
        X = _tfidf.fit_transform(sentences)
        return [X[i].toarray().flatten().tolist() for i in range(X.shape[0])]


def embed_single(rule: dict) -> list[float]:
    """Embed a single rule → vector."""
    return embed_rules([rule])[0]


def using_sbert() -> bool:
    """Whether semantic embeddings (vs TF-IDF) are active."""
    return _USE_SBERT
