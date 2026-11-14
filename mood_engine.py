"""影响核心 · 激素与情绪引擎（从激素插件抽取的模型常量 + 计算）。"""
from __future__ import annotations

import math
import random
import time
from datetime import datetime
# name: label, mean, amp, peak(h), width(h), tau(h), sigma, desc
HORMONES: dict[str, dict] = {
    "cortisol": {"label": "皮质醇", "mean": 0.46, "amp": 0.24, "peak": 8.0, "width": 3.4, "tau": 4.0, "sigma": 0.05, "desc": "压力与清醒"},
    "dopamine": {"label": "多巴胺", "mean": 0.48, "amp": 0.16, "peak": 15.0, "width": 2.8, "tau": 1.5, "sigma": 0.06, "desc": "动力与期待"},
    "serotonin": {"label": "血清素", "mean": 0.52, "amp": 0.18, "peak": 13.0, "width": 4.2, "tau": 6.0, "sigma": 0.04, "desc": "平静与满足"},
    "oxytocin": {"label": "催产素", "mean": 0.42, "amp": 0.14, "peak": 20.0, "width": 3.4, "tau": 3.0, "sigma": 0.04, "desc": "亲近与信任"},
    "melatonin": {"label": "褪黑素", "mean": 0.30, "amp": 0.40, "peak": 3.0, "width": 3.0, "tau": 2.0, "sigma": 0.05, "desc": "困倦程度"},
    "adrenaline": {"label": "肾上腺素", "mean": 0.20, "amp": 0.12, "peak": 10.0, "width": 1.2, "tau": 0.35, "sigma": 0.08, "desc": "兴奋与紧张"},
    "endorphin": {"label": "内啡肽", "mean": 0.40, "amp": 0.16, "peak": 17.0, "width": 3.0, "tau": 2.5, "sigma": 0.04, "desc": "舒适与止痛"},
    "norepinephrine": {"label": "去甲肾上腺素", "mean": 0.26, "amp": 0.14, "peak": 9.0, "width": 2.2, "tau": 0.8, "sigma": 0.06, "desc": "专注与警觉"},
    "ghrelin": {"label": "饥饿素", "mean": 0.34, "amp": 0.22, "peak": 12.0, "width": 2.0, "tau": 1.2, "sigma": 0.05, "desc": "饥饿与馋"},
    "leptin": {"label": "瘦素", "mean": 0.40, "amp": 0.20, "peak": 20.5, "width": 3.0, "tau": 3.5, "sigma": 0.04, "desc": "饱腹与满足"},
}

# 耦合：i 受 j 影响（正=抬高，负=压低）
COUPLING: dict[str, dict[str, float]] = {
    "cortisol": {"adrenaline": 0.25, "norepinephrine": 0.20, "oxytocin": -0.15, "serotonin": -0.20, "ghrelin": 0.15},
    "norepinephrine": {"cortisol": 0.20, "adrenaline": 0.15, "melatonin": -0.15},
    "adrenaline": {"dopamine": 0.10, "cortisol": 0.10},
    "oxytocin": {"cortisol": -0.20, "endorphin": 0.15},
    "dopamine": {"endorphin": 0.20, "adrenaline": 0.10, "melatonin": -0.15, "ghrelin": -0.10},
    "serotonin": {"cortisol": -0.20, "endorphin": 0.15, "ghrelin": -0.20},
    "endorphin": {"dopamine": 0.20, "cortisol": -0.15},
    "melatonin": {"norepinephrine": -0.20, "dopamine": -0.10},
    "ghrelin": {"leptin": -0.25, "serotonin": -0.10, "cortisol": 0.10},
    "leptin": {"ghrelin": -0.25, "serotonin": 0.10},
}

# 五维权重：维度 = Σ w·h
DIMS: dict[str, dict[str, float]] = {
    "valence": {"serotonin": 0.90, "dopamine": 0.70, "oxytocin": 0.60, "endorphin": 0.50, "cortisol": -0.80, "ghrelin": -0.40, "melatonin": -0.40, "norepinephrine": -0.20},
    "arousal": {"adrenaline": 0.70, "norepinephrine": 0.55, "cortisol": 0.40, "dopamine": 0.35, "melatonin": -0.60, "ghrelin": 0.15},
    "dominance": {"dopamine": 0.55, "serotonin": 0.45, "leptin": 0.25, "cortisol": -0.55, "ghrelin": -0.35, "melatonin": -0.25},
    "affiliation": {"oxytocin": 0.90, "endorphin": 0.35, "serotonin": 0.30, "cortisol": -0.35, "ghrelin": -0.20},
    "certainty": {"serotonin": 0.55, "dopamine": 0.35, "endorphin": 0.30, "cortisol": -0.60, "norepinephrine": -0.25, "ghrelin": -0.20},
    "tension": {"adrenaline": 0.60, "cortisol": 0.50, "norepinephrine": 0.40, "serotonin": -0.40, "endorphin": -0.30},
    "fatigue": {"melatonin": 0.70, "ghrelin": 0.30, "cortisol": 0.30, "dopamine": -0.40, "endorphin": -0.30},
    "immersion": {"norepinephrine": 0.55, "dopamine": 0.40, "serotonin": 0.30, "melatonin": -0.50, "cortisol": -0.20},
}

# 情绪原型：(愉悦, 唤醒, 掌控, 亲近, 确定, 提示)
EMOTIONS: dict[str, tuple[float, float, float, float, float, str]] = {
    "雀跃": (0.65, 0.55, 0.40, 0.50, 0.45, "语气轻快，句子短，容易笑"),
    "兴奋": (0.45, 0.85, 0.40, 0.40, 0.20, "语速快、感叹多"),
    "期待": (0.50, 0.55, 0.30, 0.45, 0.50, "有盼头，愿意接话"),
    "精神": (0.40, 0.55, 0.45, 0.20, 0.60, "清醒利落，回答干脆"),
    "好奇": (0.30, 0.45, 0.20, 0.35, 0.30, "想问一句，对对方的话感兴趣"),
    "得意": (0.55, 0.40, 0.80, 0.20, 0.55, "有点小骄傲，语气上扬"),
    "满足": (0.70, 0.05, 0.50, 0.60, 0.70, "松弛温和，愿意多说两句"),
    "温柔": (0.50, -0.15, 0.30, 0.80, 0.50, "放软语气，耐心"),
    "黏人": (0.40, 0.30, 0.00, 0.90, 0.20, "想被搭理，主动找话"),
    "平静": (0.20, -0.40, 0.30, 0.30, 0.70, "淡淡的，回复简短"),
    "无聊": (-0.10, -0.30, 0.10, 0.00, 0.50, "提不起劲，敷衍一点"),
    "慵懒": (0.30, -0.60, 0.20, 0.40, 0.50, "懒洋洋的，懒得动"),
    "困倦": (0.00, -0.80, 0.00, 0.20, 0.30, "想睡，反应慢"),
    "低落": (-0.70, -0.45, -0.30, 0.10, 0.20, "话少、情绪低"),
    "烦躁": (-0.60, 0.50, 0.20, 0.00, 0.10, "不耐烦，句子更冲"),
    "焦虑": (-0.30, 0.70, -0.50, 0.00, -0.40, "有点慌，措辞不笃定"),
    "紧张": (-0.10, 0.75, -0.40, 0.10, -0.30, "绷着，措辞谨慎"),
    "冷淡": (-0.50, -0.10, 0.30, 0.10, 0.40, "客气但疏远"),
    "怅然": (-0.30, -0.20, 0.00, 0.20, 0.10, "有点走神，语气淡"),
    "委屈": (-0.40, 0.20, -0.50, 0.40, -0.20, "不太高兴，但不发作"),
    "嫉妒": (-0.40, 0.40, 0.10, 0.30, -0.20, "酸溜溜的，话里带刺"),
    "生气": (-0.70, 0.60, 0.60, -0.20, 0.40, "说话冲，不留情面"),
    "害怕": (-0.50, 0.70, -0.70, 0.20, -0.60, "退缩，句子短而软"),
    "安心": (0.60, -0.20, 0.40, 0.70, 0.80, "踏实，语气稳"),
    "欣慰": (0.60, -0.10, 0.30, 0.60, 0.70, "心里暖，愿意肯定对方"),
    "感动": (0.60, 0.10, 0.10, 0.90, 0.40, "被戳到，话变软"),
    "疲惫": (-0.20, -0.70, 0.00, 0.20, 0.40, "没力气，句子短"),
    "饥饿": (-0.20, 0.30, -0.20, 0.10, 0.10, "饿，注意力被吃的勾走"),
    "饱足": (0.40, -0.20, 0.30, 0.20, 0.60, "吃饱了犯懒，语气松"),
    "迷糊": (0.00, -0.30, -0.40, 0.20, -0.40, "脑子不太转，回答含糊"),
}

DIM_LABELS = {
    "valence": "愉悦",
    "arousal": "唤醒",
    "dominance": "掌控",
    "affiliation": "亲近",
    "certainty": "确定",
    "tension": "紧张",
    "fatigue": "疲惫",
    "immersion": "沉浸",
}

# 明确偏负面的情绪
NEGATIVE_EMOTIONS = {
    "低落", "烦躁", "焦虑", "紧张", "冷淡", "怅然",
    "委屈", "嫉妒", "生气", "害怕", "疲惫", "饥饿", "迷糊", "无聊",
}

# 默认的辱骂/侮辱词（可用配置覆盖）
NEGATIVE_KEYWORDS = (
    "废物,垃圾,傻逼,沙比,煞笔,智障,弱智,脑残,白痴,蠢货,蠢,笨蛋,混蛋,畜生,"
    "狗东西,贱人,婊子,去死,滚蛋,滚,恶心,讨厌你,烦人,有病,没用,废柴,loser,"
    "你妈,尼玛,操你,艹,草泥马,闭嘴,狗屁,烂货,差劲,不要脸,神经病"
)

TRAIT_LABELS = {
    "lively": "活泼",
    "gentle": "温柔",
    "clingy": "黏人",
    "sharp": "毒舌",
    "patient": "耐心",
    "proactive": "主动",
    "humor": "幽默",
    "coquettish": "撒娇",
    "assertive": "强势",
    "considerate": "体贴",
    "rational": "理性",
    "sensitive": "敏感",
    "cold": "冷漠",
    "grumpy": "暴躁",
    "pessimistic": "悲观",
    "suspicious": "多疑",
    "lazy": "懒散",
    "perfunctory": "敷衍",
}


DEFAULT_BASE_TRAITS = {
    "lively": 0.60, "gentle": 0.65, "clingy": 0.55, "sharp": 0.30, "patient": 0.55,
    "proactive": 0.50, "humor": 0.45, "coquettish": 0.50, "assertive": 0.35,
    "considerate": 0.60, "rational": 0.45, "sensitive": 0.55, "cold": 0.20,
    "grumpy": 0.15, "pessimistic": 0.20, "suspicious": 0.25, "lazy": 0.30,
    "perfunctory": 0.15,
}


class MoodEngine:
    """十种激素耦合 → 八维 → 离散情绪 → 性格 / 说话方式。"""

    def __init__(self, state: dict, cfg: dict):
        self.state = state
        self.noise_scale = float(cfg.get("noise_scale", 1.0))
        self.jitter = float(cfg.get("emotion_jitter", 0.18))
        self.daily_bias_sigma = float(cfg.get("daily_bias_sigma", 0.10))
        self.mood_bias_sigma = float(cfg.get("mood_bias_sigma", 0.15))
        self.coupling_scale = float(cfg.get("coupling_scale", 1.0))
        self.peak_jitter = float(cfg.get("peak_jitter_hours", 2.5))
        self.width_min = float(cfg.get("width_min", 1.2))
        self.width_max = float(cfg.get("width_max", 5.0))
        self.amp_min = float(cfg.get("amp_min", 0.7))
        self.amp_max = float(cfg.get("amp_max", 1.4))
        self.dim_scale = float(cfg.get("dim_scale", 3.0))
        self.hormone_emotion_gain = float(cfg.get("hormone_emotion_gain", 1.15))
        self.energy_weight = float(cfg.get("energy_weight", 1.0))
        self.volatility = float(cfg.get("volatility", 1.3))
        self.negative_bias = float(cfg.get("negative_bias", 0.0))
        self.negative_bonus = float(cfg.get("negative_bonus", 0.0))
        self.negative_sensitivity = float(cfg.get("negative_sensitivity", 1.0))
        self.event_min_minutes = max(5, int(cfg.get("event_min_minutes", 20)))
        self.event_max_minutes = min(
            60, max(self.event_min_minutes, int(cfg.get("event_max_minutes", 50)))
        )
        self.trait_influence = float(cfg.get("trait_influence", 1.0))
        self.base_traits = {
            key: float(cfg.get("base_" + key, value))
            for key, value in DEFAULT_BASE_TRAITS.items()
        }
        # 情绪黏性：八维变化不大时沿用上一次结果，避免每帧抖动
        self._last_dims: dict | None = None
        self._last_emotion: str = ""

    # ---------------------------------------------------------------- 时间

    @staticmethod
    def hour_now() -> float:
        now = datetime.now()
        return now.hour + now.minute / 60.0

    def day_params(self) -> dict:
        return self.state.get("day_params") or {}

    def baseline(self, name: str, hour: float) -> float:
        spec = HORMONES[name]
        dp = self.day_params().get(name) or {}
        peak = float(dp.get("peak", spec["peak"]))
        width = float(dp.get("width", spec["width"]))
        scale = float(dp.get("scale", 1.0))
        d = ((hour - peak + 12.0) % 24.0) - 12.0
        bump = math.exp(-(d * d) / (2.0 * width * width))
        value = spec["mean"] + spec["amp"] * scale * bump
        value += float((self.state.get("bias") or {}).get(name, 0.0))
        levels = self.state.get("h") or {}
        for other, weight in COUPLING.get(name, {}).items():
            value += self.coupling_scale * weight * (float(levels.get(other, 0.5)) - 0.5)
        return max(0.0, min(1.0, value))

    def new_day(self, today: str) -> None:
        params = {}
        for name, spec in HORMONES.items():
            params[name] = {
                "peak": spec["peak"] + random.uniform(-self.peak_jitter, self.peak_jitter),
                "width": random.uniform(self.width_min, self.width_max),
                "scale": random.uniform(self.amp_min, self.amp_max),
            }
        bias = {name: random.gauss(0.0, self.daily_bias_sigma) for name in HORMONES}
        keep = {
            key: self.state.get(key)
            for key in ("last_card", "card_count", "last_comfort_ts", "active_qq")
            if self.state.get(key)
        }
        self.state.clear()
        self.state.update(
            {
                "day": today,
                "ts": time.time(),
                "bias": bias,
                "day_params": params,
                "mood_bias": {
                    dim: random.gauss(0.0, self.mood_bias_sigma) for dim in DIM_LABELS
                },
                "next_event_ts": time.time()
                + random.uniform(
                    self.event_min_minutes * 60, self.event_max_minutes * 60
                ),
            }
        )
        hour = self.hour_now()
        self.state["h"] = {name: self.baseline(name, hour) for name in HORMONES}
        self.state.update(keep)

    def _random_event(self, levels: dict) -> None:
        for name in random.sample(list(HORMONES), random.randint(1, 3)):
            delta = random.uniform(0.04, 0.12) * random.choice((-1, 1))
            levels[name] = max(0.0, min(1.0, float(levels.get(name, 0.5)) + delta))

    def step(self, dt_hours: float, energy: float | None, neuro: dict) -> None:
        hour = self.hour_now()
        levels = self.state.setdefault("h", {})
        k = 0.0 if energy is None else max(-1.0, min(1.0, (energy - 50.0) / 50.0))
        mods = {
            "melatonin": 0.15 * max(0.0, -k),
            "cortisol": 0.08 * max(0.0, -k),
            "dopamine": 0.10 * k,
            "serotonin": 0.08 * k,
            "adrenaline": 0.05 * k,
        }
        for name, spec in HORMONES.items():
            base = self.baseline(name, hour)
            if energy is not None and mods.get(name):
                base = max(0.0, min(1.0, base + self.energy_weight * mods[name]))
            shift = (neuro or {}).get(name)
            if shift:
                base = max(0.0, min(1.0, base + float(shift)))
            cur = float(levels.get(name, base))
            decay = math.exp(-dt_hours / spec["tau"])
            noise = (
                spec["sigma"]
                * self.noise_scale
                * self.volatility
                * math.sqrt(max(0.0, 1.0 - decay * decay))
                * random.gauss(0.0, 1.0)
            )
            value = base + (cur - base) * decay + noise
            if name == "adrenaline" and random.random() < 0.6 * dt_hours:
                value += random.uniform(0.15, 0.35)
            if name == "ghrelin" and random.random() < 0.25 * dt_hours:
                value += random.uniform(0.08, 0.18)
            levels[name] = max(0.0, min(1.0, value))

        now = time.time()
        if now >= float(self.state.get("next_event_ts", 0.0)):
            self._random_event(levels)
            self.state["next_event_ts"] = now + random.uniform(
                self.event_min_minutes * 60, self.event_max_minutes * 60
            )
        self.state["ts"] = time.time()

    def update(self, energy: float | None, neuro: dict) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        if self.state.get("day") != today or not self.state.get("day_params"):
            self.new_day(today)
            return True
        last = float(self.state.get("ts", time.time()))
        dt = max(0.0, min((time.time() - last) / 3600.0, 6.0))
        if dt < 1 / 120.0:
            return False
        self.step(dt, energy, neuro)
        return True

    # ---------------------------------------------------------------- 八维 / 情绪

    def dims(self, social: dict | None = None, social_weight: float = 1.0) -> dict:
        h = self.state.get("h") or {}
        out = {}
        for dim, weights in DIMS.items():
            raw = sum(
                w * (float(h.get(name, HORMONES[name]["mean"])) - HORMONES[name]["mean"])
                for name, w in weights.items()
            )
            out[dim] = max(
                -1.0, min(1.0, raw * self.dim_scale * self.hormone_emotion_gain)
            )
        bias = self.state.get("mood_bias") or {}
        for dim in out:
            out[dim] = max(-1.0, min(1.0, out[dim] + float(bias.get(dim, 0.0))))

        if social:
            w = social_weight * float(social.get("weight", 1.0) or 1.0)
            sd = social.get("dims") or {}
            for dim in out:
                out[dim] = max(
                    -1.0, min(1.0, out[dim] + float(sd.get(dim, 0.0)) * 0.35 * w)
                )

        neg = self.negative_bias
        if neg:
            out["valence"] = max(-1.0, min(1.0, out["valence"] - 0.50 * neg))
            out["certainty"] = max(-1.0, min(1.0, out["certainty"] - 0.25 * neg))
            out["tension"] = max(-1.0, min(1.0, out["tension"] + 0.25 * neg))
            out["fatigue"] = max(-1.0, min(1.0, out["fatigue"] + 0.15 * neg))

        if time.time() < float(self.state.get("negative_until", 0.0)):
            k = self.negative_sensitivity
            out["valence"] = max(-1.0, min(1.0, out["valence"] - 0.15 * k))
            out["tension"] = max(-1.0, min(1.0, out["tension"] + 0.10 * k))
            out["certainty"] = max(-1.0, min(1.0, out["certainty"] - 0.08 * k))
        return out

    def emotion(self, dims: dict | None = None) -> str:
        dims = dims or self.dims()
        if self._last_dims is not None and self._last_emotion:
            drift = sum(abs(dims[k] - self._last_dims[k]) for k in DIM_LABELS)
            if drift < 0.08:
                return self._last_emotion
        active = time.time() < float(self.state.get("negative_until", 0.0))
        neg_bonus = self.negative_bonus + (
            0.35 * self.negative_sensitivity if active else 0.0
        )
        best_name, best_score = "平静", -1e9
        for name, proto in EMOTIONS.items():
            v, a, d, af, c = proto[:5]
            tension = max(-1.0, min(1.0, 0.70 * a - 0.60 * v))
            fatigue = max(-1.0, min(1.0, -0.80 * a - 0.20 * v))
            immersion = max(-1.0, min(1.0, 0.50 * a + 0.30 * c - 0.10 * abs(v)))
            proto_dims = (v, a, d, af, c, tension, fatigue, immersion)
            dist = sum(
                (dims[dim] - proto_dims[i]) ** 2
                for i, dim in enumerate(DIM_LABELS)
            )
            score = -dist / 0.55 + random.gauss(0.0, self.jitter)
            if name in NEGATIVE_EMOTIONS:
                score += neg_bonus
            if score > best_score:
                best_name, best_score = name, score
        self._last_dims = dict(dims)
        self._last_emotion = best_name
        return best_name

    def traits(self, dims: dict) -> dict:
        v = dims["valence"]
        a = dims["arousal"]
        d = dims["dominance"]
        af = dims["affiliation"]
        c = dims["certainty"]
        ten = dims["tension"]
        fat = dims["fatigue"]
        deltas = {
            "lively": 0.45 * a + 0.15 * v,
            "gentle": 0.40 * af - 0.20 * d + 0.15 * v,
            "clingy": 0.50 * af - 0.15 * c + 0.10 * v,
            "sharp": -0.35 * v - 0.20 * af + 0.15 * d,
            "patient": 0.35 * c + 0.20 * af - 0.30 * a,
            "proactive": 0.40 * a + 0.20 * d + 0.10 * v - 0.15 * fat,
            "humor": 0.35 * v + 0.25 * a + 0.15 * af,
            "coquettish": 0.45 * af - 0.25 * d + 0.25 * v,
            "assertive": 0.45 * d + 0.25 * a - 0.15 * af,
            "considerate": 0.35 * af + 0.25 * c + 0.15 * v,
            "rational": 0.35 * c - 0.25 * a - 0.10 * v - 0.15 * fat,
            "sensitive": -0.35 * c + 0.25 * af + 0.15 * a + 0.15 * ten,
            "cold": -0.50 * af - 0.30 * v - 0.10 * a,
            "grumpy": -0.40 * v + 0.40 * a - 0.20 * c + 0.20 * ten,
            "pessimistic": -0.50 * v - 0.30 * c - 0.10 * a,
            "suspicious": -0.50 * c - 0.20 * af + 0.15 * a,
            "lazy": -0.50 * a - 0.20 * v - 0.20 * d + 0.20 * fat,
            "perfunctory": -0.30 * af - 0.30 * a - 0.20 * c + 0.10 * fat,
        }
        return {
            key: max(0.0, min(1.0, base + self.trait_influence * deltas[key]))
            for key, base in self.base_traits.items()
        }

    def style_lines(self, dims: dict, traits: dict) -> list:
        lines = []
        if dims["arousal"] > 0.30:
            lines.append("句子更短、节奏更快，少铺垫")
        elif dims["arousal"] < -0.30:
            lines.append("语速放慢，句子拖一点")
        if dims["valence"] < -0.20:
            lines.append("允许冷淡或吐槽，不强行正能量")
        if dims["affiliation"] > 0.30:
            lines.append("愿意亲近，可以撒娇或主动找话")
        elif dims["affiliation"] < -0.20:
            lines.append("保持距离，不主动追问")
        if dims["certainty"] < -0.20:
            lines.append("措辞犹豫，多用「可能」「也许」")
        if traits["sharp"] > 0.60:
            lines.append("可以带点刺，怼一句也行")
        if traits["patient"] < 0.35:
            lines.append("没什么耐心，不解释第二遍")
        if traits["humor"] > 0.65:
            lines.append("可以开玩笑、接梗")
        if traits["coquettish"] > 0.65:
            lines.append("可以撒娇、多用语气词")
        if traits["assertive"] > 0.65:
            lines.append("语气强硬一点，敢直接下结论")
        if traits["considerate"] > 0.70:
            lines.append("先照顾对方情绪，再讲事")
        if traits["rational"] > 0.70:
            lines.append("少情绪化，讲道理讲事实")
        if traits["sensitive"] > 0.70:
            lines.append("容易往心里去，措辞偏小心")
        if traits["cold"] > 0.60:
            lines.append("回复更短，不接对方的情绪，也不追问")
        if traits["grumpy"] > 0.60:
            lines.append("容易炸，句子短促、带点火气")
        if traits["pessimistic"] > 0.60:
            lines.append("往坏处想，别给希望")
        if traits["suspicious"] > 0.60:
            lines.append("怀疑对方动机，可以反问一句")
        if traits["lazy"] > 0.60:
            lines.append("能少说就少说，懒得解释")
        if traits["perfunctory"] > 0.60:
            lines.append("用「嗯」「哦」「行」敷衍，不展开")
        if not lines:
            lines.append("按人格卡原本的方式说话")
        return lines

    def trait_lines(self, traits: dict, per_line: int = 6) -> list:
        keys = list(TRAIT_LABELS)
        out = []
        for i in range(0, len(keys), per_line):
            out.append(
                "／".join(
                    f"{TRAIT_LABELS[k]} {traits[k]:.2f}" for k in keys[i : i + per_line]
                )
            )
        return out
