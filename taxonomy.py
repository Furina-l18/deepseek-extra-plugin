"""情感维度、情绪类型与关键词词库。

维度沿用情绪激素插件的八维，保证两边可以直接对接；
情绪类型 20 种（要求至少 15 种）。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 八维

DIM_LABELS: dict[str, str] = {
    "valence": "愉悦",
    "arousal": "唤醒",
    "dominance": "掌控",
    "affiliation": "亲近",
    "certainty": "确定",
    "tension": "紧张",
    "fatigue": "疲惫",
    "immersion": "沉浸",
}
DIM_KEYS: list[str] = list(DIM_LABELS)

# ---------------------------------------------------------------- 二十种情绪

EMOTION_TYPES: list[str] = [
    "开心",
    "满足",
    "兴奋",
    "期待",
    "亲近",
    "感激",
    "平静",
    "好奇",
    "信任",
    "疲惫",
    "无聊",
    "低落",
    "焦虑",
    "生气",
    "委屈",
    "失望",
    "嫉妒",
    "孤独",
    "紧张",
    "愧疚",
]

NEGATIVE_TYPES: set[str] = {
    "疲惫", "无聊", "低落", "焦虑", "生气",
    "委屈", "失望", "嫉妒", "孤独", "紧张", "愧疚",
}
POSITIVE_TYPES: set[str] = set(EMOTION_TYPES) - NEGATIVE_TYPES

# 每种情绪的八维先验中心，用于缺省补全与回退估计
TYPE_CENTERS: dict[str, dict[str, float]] = {
    "开心": {"valence": 0.7, "arousal": 0.4, "dominance": 0.3, "affiliation": 0.5, "certainty": 0.4, "tension": -0.3, "fatigue": -0.3, "immersion": 0.3},
    "满足": {"valence": 0.6, "arousal": -0.2, "dominance": 0.4, "affiliation": 0.5, "certainty": 0.6, "tension": -0.5, "fatigue": -0.1, "immersion": 0.1},
    "兴奋": {"valence": 0.6, "arousal": 0.8, "dominance": 0.4, "affiliation": 0.4, "certainty": 0.2, "tension": 0.2, "fatigue": -0.4, "immersion": 0.5},
    "期待": {"valence": 0.4, "arousal": 0.5, "dominance": 0.2, "affiliation": 0.4, "certainty": 0.1, "tension": 0.1, "fatigue": -0.2, "immersion": 0.4},
    "亲近": {"valence": 0.5, "arousal": 0.1, "dominance": 0.1, "affiliation": 0.85, "certainty": 0.4, "tension": -0.3, "fatigue": -0.1, "immersion": 0.3},
    "感激": {"valence": 0.6, "arousal": 0.1, "dominance": 0.0, "affiliation": 0.7, "certainty": 0.5, "tension": -0.3, "fatigue": -0.1, "immersion": 0.2},
    "平静": {"valence": 0.2, "arousal": -0.4, "dominance": 0.2, "affiliation": 0.2, "certainty": 0.5, "tension": -0.6, "fatigue": 0.0, "immersion": 0.0},
    "好奇": {"valence": 0.3, "arousal": 0.4, "dominance": 0.1, "affiliation": 0.3, "certainty": -0.1, "tension": 0.1, "fatigue": -0.1, "immersion": 0.6},
    "信任": {"valence": 0.5, "arousal": 0.0, "dominance": 0.2, "affiliation": 0.7, "certainty": 0.6, "tension": -0.4, "fatigue": -0.1, "immersion": 0.2},
    "疲惫": {"valence": -0.3, "arousal": -0.7, "dominance": -0.2, "affiliation": 0.1, "certainty": 0.2, "tension": -0.2, "fatigue": 0.9, "immersion": -0.4},
    "无聊": {"valence": -0.2, "arousal": -0.5, "dominance": 0.0, "affiliation": 0.0, "certainty": 0.3, "tension": -0.3, "fatigue": 0.3, "immersion": -0.6},
    "低落": {"valence": -0.7, "arousal": -0.4, "dominance": -0.3, "affiliation": 0.1, "certainty": 0.0, "tension": 0.1, "fatigue": 0.4, "immersion": -0.3},
    "焦虑": {"valence": -0.4, "arousal": 0.6, "dominance": -0.5, "affiliation": 0.0, "certainty": -0.6, "tension": 0.8, "fatigue": 0.2, "immersion": 0.3},
    "生气": {"valence": -0.7, "arousal": 0.6, "dominance": 0.5, "affiliation": -0.4, "certainty": 0.3, "tension": 0.7, "fatigue": 0.0, "immersion": 0.4},
    "委屈": {"valence": -0.5, "arousal": 0.2, "dominance": -0.5, "affiliation": 0.3, "certainty": -0.2, "tension": 0.3, "fatigue": 0.2, "immersion": 0.1},
    "失望": {"valence": -0.6, "arousal": -0.3, "dominance": -0.3, "affiliation": -0.1, "certainty": -0.3, "tension": 0.1, "fatigue": 0.3, "immersion": -0.2},
    "嫉妒": {"valence": -0.4, "arousal": 0.4, "dominance": 0.0, "affiliation": 0.1, "certainty": -0.2, "tension": 0.4, "fatigue": 0.0, "immersion": 0.2},
    "孤独": {"valence": -0.5, "arousal": -0.3, "dominance": -0.2, "affiliation": -0.6, "certainty": 0.0, "tension": 0.0, "fatigue": 0.2, "immersion": -0.3},
    "紧张": {"valence": -0.2, "arousal": 0.7, "dominance": -0.4, "affiliation": 0.0, "certainty": -0.5, "tension": 0.9, "fatigue": 0.1, "immersion": 0.3},
    "愧疚": {"valence": -0.4, "arousal": 0.1, "dominance": -0.4, "affiliation": 0.2, "certainty": -0.2, "tension": 0.4, "fatigue": 0.1, "immersion": 0.1},
}

# ---------------------------------------------------------------- 回退词库
# 模型不可用时用关键词兜底，保证系统仍能给出一个方向正确的画像。

KEYWORD_LEXICON: dict[str, tuple[str, ...]] = {
    "开心": ("哈哈", "笑死", "开心", "高兴", "好耶", "爽", "舒服", "太棒", "nice", "哈哈"),
    "满足": ("满足", "够了", "挺好", "不错", "还行", "安心"),
    "兴奋": ("刺激", "激动", "上头", "起飞", "冲", "燃"),
    "期待": ("期待", "等不及", "想见", "盼", "下次", "以后"),
    "亲近": ("想你", "喜欢你", "抱抱", "贴贴", "亲亲", "宝", "老婆", "老公", "陪我"),
    "感激": ("谢谢", "感谢", "多谢", "麻烦你", "辛苦了", "救"),
    "平静": ("嗯", "好", "可以", "行", "没事"),
    "好奇": ("为什么", "怎么", "啥", "什么", "真的吗", "问一下"),
    "信任": ("相信", "信你", "靠你了", "交给你"),
    "疲惫": ("累", "困", "乏", "撑不住", "没力气", "熬夜", "加班"),
    "无聊": ("无聊", "没意思", "闲", "打发时间"),
    "低落": ("难受", "难过", "伤心", "emo", "想哭", "不开心", "郁闷", "烦"),
    "焦虑": ("焦虑", "慌", "担心", "害怕", "紧张", "怎么办", "来不及"),
    "生气": ("气死", "滚", "烦死", "别烦", "讨厌", "恶心", "垃圾", "有病"),
    "委屈": ("委屈", "凭什么", "明明", "欺负", "冤枉"),
    "失望": ("失望", "算了", "没救了", "白费", "呵呵"),
    "嫉妒": ("羡慕", "嫉妒", "凭什么他", "酸"),
    "孤独": ("一个人", "没人", "孤独", "寂寞", "找不到人"),
    "紧张": ("紧张", "抖", "手心", "心跳", "压力"),
    "愧疚": ("对不起", "抱歉", "我的错", "愧疚", "不好意思"),
}


# ---------------------------------------------------------------- 互动事件
# 情感来自「发生了什么」，不是「聊了多少句」。
# 权重是这件事对情感的冲击力度：辱骂最伤，闲聊不改变情感。

EVENT_LABELS: dict[str, str] = {
    "praise": "被夸奖",
    "thanks": "被感谢",
    "care": "被关心",
    "help": "被帮忙",
    "chat": "普通闲聊",
    "ignore": "被冷落",
    "reject": "被拒绝",
    "conflict": "发生争执",
    "insult": "被辱骂",
}

EVENT_WEIGHTS: dict[str, float] = {
    "praise": 0.45,
    "thanks": 0.40,
    "care": 0.35,
    "help": 0.25,
    "chat": 0.0,
    "ignore": -0.25,
    "reject": -0.30,
    "conflict": -0.45,
    "insult": -0.60,
}

EVENT_KINDS = list(EVENT_WEIGHTS)


# 带明确亲疏色彩的情绪（「平静」「好奇」这类中性词不算正面情感）
AFFECTION_POSITIVE = {"开心", "满足", "兴奋", "期待", "亲近", "感激", "信任"}


def affection_tone(emotions: dict[str, float]) -> float:
    """没有事件时的兜底：只看带明确好坏色彩的情绪。"""
    pos_items = [
        float(v)
        for k, v in emotions.items()
        if k in AFFECTION_POSITIVE and float(v) > 0
    ]
    neg_items = [
        float(v)
        for k, v in emotions.items()
        if k in NEGATIVE_TYPES and float(v) > 0
    ]
    if not pos_items and not neg_items:
        return 0.0
    pos = sum(pos_items)
    neg = sum(neg_items)
    total = pos + neg
    direction = (pos - neg) / total
    strength = total / max(1, len(pos_items) + len(neg_items))
    return clamp(direction * strength)


def event_tone(events: list[dict]) -> float:
    """按事件种类和强度算这段互动的冲击，与消息条数无关。

    只有普通闲聊时返回 0——聊得多不会自动变成正面情感。
    """
    total = 0.0
    for item in events or []:
        if not isinstance(item, dict):
            continue
        weight = EVENT_WEIGHTS.get(str(item.get("kind") or ""), 0.0)
        if weight == 0.0:
            continue
        try:
            intensity = float(item.get("intensity", 0.0))
        except (TypeError, ValueError):
            continue
        if intensity <= 0:
            continue
        total += weight * min(1.0, intensity)
    return clamp(total)


def events_to_text(events: list[dict], limit: int = 4) -> str:
    """把事件压成一行，给命令和页面用。"""
    parts = []
    for item in (events or [])[:limit]:
        if not isinstance(item, dict):
            continue
        label = EVENT_LABELS.get(str(item.get("kind") or ""), "")
        if not label:
            continue
        try:
            intensity = float(item.get("intensity", 0.0))
        except (TypeError, ValueError):
            intensity = 0.0
        parts.append(f"{label} {intensity:.2f}")
    return "、".join(parts)


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


# ---------------------------------------------------------------- 长期情感（正/中/负）

SENTIMENT_POS = "正"
SENTIMENT_NEU = "中"
SENTIMENT_NEG = "负"
SENTIMENT_ORDER = (SENTIMENT_POS, SENTIMENT_NEU, SENTIMENT_NEG)

POS_THRESHOLD = 0.15
NEG_THRESHOLD = -0.15
HYSTERESIS = 0.05


def sentiment_score(dims: dict[str, float]) -> float:
    """由八维折算长期情感分：愉悦为主，亲近加成，紧张扣分。"""
    valence = float(dims.get("valence", 0.0))
    affiliation = float(dims.get("affiliation", 0.0))
    certainty = float(dims.get("certainty", 0.0))
    tension = float(dims.get("tension", 0.0))
    raw = 0.60 * valence + 0.30 * affiliation + 0.10 * certainty - 0.15 * tension
    return clamp(raw)


def interaction_tone(emotions: dict[str, float]) -> float:
    """这段互动让机器人感觉如何：正面情绪加分，负面情绪扣分。

    结果 = 方向（正负相抵后归一）× 平均强度，
    这样「轻微开心」不会和「非常亲近」拿同一个满分。
    """
    pos_items = [
        float(v)
        for k, v in emotions.items()
        if k in POSITIVE_TYPES and float(v) > 0
    ]
    neg_items = [
        float(v)
        for k, v in emotions.items()
        if k in NEGATIVE_TYPES and float(v) > 0
    ]
    if not pos_items and not neg_items:
        return 0.0
    pos = sum(pos_items)
    neg = sum(neg_items)
    total = pos + neg
    direction = (pos - neg) / total
    strength = total / max(1, len(pos_items) + len(neg_items))
    return clamp(direction * strength)


# ---------------------------------------------------------------- 具体情感类型
# 正/中/负只是极性；真正描述关系的是这些词（广义的「爱」「恨」）。
# 每个类型给出：中文、极性、理想分数、以及支撑它的情绪信号。

SENTIMENT_SPECS: dict[str, dict] = {
    # ---------------- 正面
    "love": {"label": "爱", "polarity": "pos", "ideal": 0.75,
             "signals": {"亲近": 1.0, "信任": 0.8, "满足": 0.3}},
    "intimacy": {"label": "亲密", "polarity": "pos", "ideal": 0.60,
                 "signals": {"亲近": 1.0, "感激": 0.3}},
    "admiration": {"label": "崇拜", "polarity": "pos", "ideal": 0.60,
                   "signals": {"期待": 0.5, "好奇": 0.5}},
    "attachment": {"label": "依恋", "polarity": "pos", "ideal": 0.55,
                   "signals": {"期待": 0.8, "亲近": 0.8}},
    "trust": {"label": "信任", "polarity": "pos", "ideal": 0.45,
              "signals": {"信任": 1.0}},
    "respect": {"label": "敬重", "polarity": "pos", "ideal": 0.45,
                "signals": {"信任": 0.5, "满足": 0.3}},
    "reliance": {"label": "依赖", "polarity": "pos", "ideal": 0.40,
                 "signals": {"期待": 0.6, "亲近": 0.5}},
    "appreciation": {"label": "欣赏", "polarity": "pos", "ideal": 0.40,
                     "signals": {"好奇": 0.5, "满足": 0.4}},
    "gratitude": {"label": "感激", "polarity": "pos", "ideal": 0.40,
                  "signals": {"感激": 1.0}},
    "security": {"label": "安心", "polarity": "pos", "ideal": 0.35,
                 "signals": {"满足": 0.6, "信任": 0.4}},
    "liking": {"label": "喜欢", "polarity": "pos", "ideal": 0.35,
               "signals": {"开心": 0.6, "满足": 0.5, "亲近": 0.4}},
    "tender": {"label": "怜惜", "polarity": "pos", "ideal": 0.30,
               "signals": {"亲近": 0.5, "期待": 0.3}},
    "protective": {"label": "保护欲", "polarity": "pos", "ideal": 0.30,
                   "signals": {"亲近": 0.6, "满足": 0.2}},
    "nostalgia": {"label": "怀念", "polarity": "pos", "ideal": 0.25,
                  "signals": {"满足": 0.4, "亲近": 0.3}},
    # ---------------- 中性
    "curious": {"label": "好奇", "polarity": "neu", "ideal": 0.15,
                "signals": {"好奇": 1.0}},
    "familiar": {"label": "熟悉", "polarity": "neu", "ideal": 0.10,
                 "signals": {"平静": 0.5, "满足": 0.3}},
    "polite": {"label": "客气", "polarity": "neu", "ideal": 0.05,
               "signals": {"平静": 0.6}},
    "watching": {"label": "观望", "polarity": "neu", "ideal": 0.00,
                 "signals": {"好奇": 0.6, "紧张": 0.3}},
    "pity": {"label": "怜悯", "polarity": "neu", "ideal": -0.05,
             "signals": {"失望": 0.3, "亲近": 0.3}},
    "plain": {"label": "平淡", "polarity": "neu", "ideal": 0.00,
              "signals": {"平静": 0.8}},
    "indifference": {"label": "漠然", "polarity": "neu", "ideal": 0.00,
                     "signals": {}},
    # ---------------- 负面
    "hate": {"label": "恨", "polarity": "neg", "ideal": -0.70,
             "signals": {"生气": 1.0}},
    "hostility": {"label": "敌意", "polarity": "neg", "ideal": -0.60,
                  "signals": {"生气": 0.8, "紧张": 0.4}},
    "disgust": {"label": "厌恶", "polarity": "neg", "ideal": -0.50,
                "signals": {"嫉妒": 0.6, "生气": 0.4}},
    "fear": {"label": "畏惧", "polarity": "neg", "ideal": -0.50,
             "signals": {"紧张": 0.9, "焦虑": 0.5}},
    "resentment": {"label": "怨念", "polarity": "neg", "ideal": -0.40,
                   "signals": {"委屈": 1.0, "失望": 0.6}},
    "disappointed": {"label": "失望", "polarity": "neg", "ideal": -0.40,
                     "signals": {"失望": 1.0}},
    "weariness": {"label": "厌倦", "polarity": "neg", "ideal": -0.35,
                  "signals": {"疲惫": 0.9, "无聊": 0.8}},
    "contempt": {"label": "轻视", "polarity": "neg", "ideal": -0.35,
                 "signals": {"无聊": 0.6, "生气": 0.3}},
    "wariness": {"label": "戒备", "polarity": "neg", "ideal": -0.30,
                 "signals": {"紧张": 0.8, "焦虑": 0.6}},
    "jealousy": {"label": "嫉妒", "polarity": "neg", "ideal": -0.30,
                 "signals": {"嫉妒": 1.0}},
    "suspicion": {"label": "猜疑", "polarity": "neg", "ideal": -0.30,
                  "signals": {"紧张": 0.5, "焦虑": 0.5}},
    "aversion": {"label": "反感", "polarity": "neg", "ideal": -0.25,
                 "signals": {"无聊": 0.5, "疲惫": 0.4}},
    "estranged": {"label": "疏离", "polarity": "neg", "ideal": -0.20,
                  "signals": {"孤独": 0.7, "无聊": 0.4}},
    "helpless": {"label": "无奈", "polarity": "neg", "ideal": -0.20,
                 "signals": {"疲惫": 0.5, "失望": 0.4}},
    "indebted": {"label": "亏欠", "polarity": "neg", "ideal": -0.15,
                 "signals": {"愧疚": 1.0}},
}

SENTIMENT_TYPES: dict[str, str] = {
    key: spec["label"] for key, spec in SENTIMENT_SPECS.items()
}
SENTIMENT_POSITIVE_TYPES = {
    key for key, spec in SENTIMENT_SPECS.items() if spec["polarity"] == "pos"
}
SENTIMENT_NEGATIVE_TYPES = {
    key for key, spec in SENTIMENT_SPECS.items() if spec["polarity"] == "neg"
}


def classify_sentiment(
    score: float,
    emotions: dict[str, float],
    pos_threshold: float = POS_THRESHOLD,
    neg_threshold: float = NEG_THRESHOLD,
) -> str:
    """长期分数 + 情绪证据打分，选最贴合的类型。

    分数决定大方向，证据决定具体用哪个词。
    类型极性必须与三档标签一致：判为中时不会冒出「爱」「恨」。
    """
    best_key = "indifference"
    best_fit = -1e9
    for key, spec in SENTIMENT_SPECS.items():
        ideal = float(spec.get("ideal", 0.0))
        dist = min(1.0, abs(score - ideal) / 1.5)
        fit = 2.4 * (1.0 - dist)

        signals = spec.get("signals") or {}
        evidence = 0.0
        for emo, weight in signals.items():
            evidence += float(weight) * float(emotions.get(emo, 0.0))
        if signals and evidence <= 0.0:
            evidence = -0.3
        fit += 1.6 * evidence

        polarity = spec.get("polarity")
        if polarity == "pos" and score < pos_threshold:
            fit -= 1.6
        elif polarity == "neg" and score > neg_threshold:
            fit -= 1.6
        elif polarity == "neu" and (
            score >= pos_threshold or score <= neg_threshold
        ):
            fit -= 1.2

        if fit > best_fit:
            best_key, best_fit = key, fit
    return best_key


def sentiment_type_label(key: str) -> str:
    return SENTIMENT_TYPES.get(key, "漠然")


# ---------------------------------------------------------------- 情感 → 神经化学
# 依据神经调质研究：催产素/内啡肽对应依恋与安全，多巴胺对应奖赏，
# 血清素对应情绪稳定，皮质醇/肾上腺素对应威胁与唤醒。
# 数值是「相对基线的持续偏移」，不是瞬时脉冲。

NEUROCHEM_PROFILE: dict[str, dict[str, float]] = {
    "love": {"oxytocin": 0.10, "endorphin": 0.06, "dopamine": 0.04, "cortisol": -0.04},
    "intimacy": {"oxytocin": 0.09, "endorphin": 0.05, "cortisol": -0.03},
    "attachment": {"oxytocin": 0.08, "dopamine": 0.04, "cortisol": -0.03},
    "admiration": {"dopamine": 0.06, "oxytocin": 0.04},
    "trust": {"oxytocin": 0.08, "serotonin": 0.05, "cortisol": -0.04},
    "respect": {"serotonin": 0.05, "oxytocin": 0.03},
    "reliance": {"oxytocin": 0.06, "dopamine": 0.03},
    "appreciation": {"dopamine": 0.05, "serotonin": 0.04},
    "gratitude": {"serotonin": 0.07, "oxytocin": 0.05, "endorphin": 0.03},
    "security": {"serotonin": 0.06, "oxytocin": 0.04, "cortisol": -0.04},
    "liking": {"dopamine": 0.05, "oxytocin": 0.03},
    "tender": {"oxytocin": 0.06, "endorphin": 0.03},
    "protective": {"oxytocin": 0.05, "dopamine": 0.03},
    "nostalgia": {"serotonin": 0.03, "endorphin": 0.03},
    # 中性
    "curious": {"dopamine": 0.03},
    "familiar": {"serotonin": 0.03},
    "pity": {"oxytocin": 0.03, "serotonin": -0.02},
    # 负面
    "hate": {"adrenaline": 0.10, "cortisol": 0.08, "serotonin": -0.07, "oxytocin": -0.08},
    "hostility": {"adrenaline": 0.08, "cortisol": 0.06, "oxytocin": -0.06},
    "disgust": {"cortisol": 0.05, "serotonin": -0.04, "oxytocin": -0.06},
    "fear": {"cortisol": 0.07, "norepinephrine": 0.06, "adrenaline": 0.05},
    "resentment": {"cortisol": 0.05, "serotonin": -0.06, "dopamine": -0.04},
    "disappointed": {"serotonin": -0.05, "dopamine": -0.05},
    "weariness": {"serotonin": -0.05, "dopamine": -0.06, "melatonin": 0.03},
    "contempt": {"cortisol": 0.04, "oxytocin": -0.05},
    "wariness": {"cortisol": 0.05, "norepinephrine": 0.05},
    "jealousy": {"cortisol": 0.05, "oxytocin": -0.05, "dopamine": -0.03},
    "suspicion": {"cortisol": 0.04, "oxytocin": -0.04},
    "aversion": {"oxytocin": -0.05, "serotonin": -0.03},
    "estranged": {"oxytocin": -0.06, "serotonin": -0.04},
    "helpless": {"dopamine": -0.06, "cortisol": 0.05},
    "indebted": {"cortisol": 0.03, "oxytocin": 0.03},
}


def neurochem_for(sentiment_key: str, intensity: float) -> dict[str, float]:
    """把情感类型换算成一组有界的神经化学偏移。"""
    base = NEUROCHEM_PROFILE.get(sentiment_key) or {}
    if not base:
        return {}
    k = max(0.0, min(1.0, intensity))
    return {name: round(delta * k, 4) for name, delta in base.items()}


# 类型数量必须至少是维度数的两倍
MIN_TYPES_PER_DIM = 2


def taxonomy_ok() -> bool:
    need = MIN_TYPES_PER_DIM * len(DIM_KEYS)
    return len(EMOTION_TYPES) >= need and len(SENTIMENT_TYPES) >= need


def sentiment_label(
    score: float,
    prev: str | None = None,
    pos_threshold: float = POS_THRESHOLD,
    neg_threshold: float = NEG_THRESHOLD,
    hysteresis: float = HYSTERESIS,
) -> str:
    """三档判定，带滞回避免在阈值附近来回跳。"""
    if score >= pos_threshold:
        return SENTIMENT_POS
    if score <= neg_threshold:
        return SENTIMENT_NEG
    if prev == SENTIMENT_POS and score > hysteresis:
        return SENTIMENT_POS
    if prev == SENTIMENT_NEG and score < -hysteresis:
        return SENTIMENT_NEG
    return SENTIMENT_NEU


def sentiment_trend(history: list[dict], score: float, window: int = 7) -> str:
    """和若干天前比较，判断升温 / 降温 / 稳定。"""
    if not history:
        return "稳定"
    past = history[-window]["score"] if len(history) >= window else history[0]["score"]
    delta = score - float(past)
    if delta > 0.05:
        return "升温"
    if delta < -0.05:
        return "降温"
    return "稳定"


def positive_ratio(emotions: dict[str, float]) -> float:
    """正面情绪占比，用于影响能量。"""
    total = sum(max(0.0, float(v)) for v in emotions.values())
    if total <= 0.0:
        return 0.5
    pos = sum(max(0.0, float(emotions.get(k, 0.0))) for k in POSITIVE_TYPES)
    return max(0.0, min(1.0, pos / total))


def empty_emotions() -> dict[str, float]:
    return {name: 0.0 for name in EMOTION_TYPES}
