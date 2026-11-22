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
        self.random_event_enabled = bool(cfg.get("random_event_enabled", False))
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
        # 情绪调控：迟滞、强度、混合、余味
        self.switch_margin = float(cfg.get("emotion_switch_margin", 0.18))
        self.dwell_seconds = max(0, int(cfg.get("emotion_dwell_seconds", 120)))
        self.blend_gap = float(cfg.get("emotion_blend_gap", 0.30))
        self.aftertaste_minutes = max(0, int(cfg.get("emotion_aftertaste_minutes", 12)))
        self.smooth_seconds = max(1.0, float(cfg.get("emotion_smooth_seconds", 60)))
        self.mood_seconds = max(300.0, float(cfg.get("mood_smooth_seconds", 2400)))
        self.ramp_seconds = max(0.0, float(cfg.get("emotion_ramp_seconds", 90)))
        self.burst_threshold = max(0.05, float(cfg.get("emotion_burst_threshold", 0.35)))
        self.burst_seconds = max(0.0, float(cfg.get("emotion_burst_seconds", 25)))
        self.emotion_jitter_floor = float(cfg.get("emotion_jitter_floor", 0.05))
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

    def circadian(self, name: str, hour: float) -> float:
        """一天里这个时刻「本该有」的水平：只有昼夜形状，不含事件与偏置。"""
        spec = HORMONES[name]
        dp = self.day_params().get(name) or {}
        peak = float(dp.get("peak", spec["peak"]))
        width = float(dp.get("width", spec["width"]))
        scale = float(dp.get("scale", 1.0))
        d = ((hour - peak + 12.0) % 24.0) - 12.0
        bump = math.exp(-(d * d) / (2.0 * width * width))
        return spec["mean"] + spec["amp"] * scale * bump

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

    @staticmethod
    def _dead(v: float, floor: float = 0.015, cap: float = 0.08) -> float:
        """给每天的起点偏置设一个死区：证据太薄就当 0，别凭空给方向。"""
        v = float(v)
        if abs(v) < floor:
            return 0.0
        return max(-cap, min(cap, v))

    def derive_day(self, evidence: dict | None = None) -> tuple[dict, dict, list]:
        """每天起点只由证据推出来；没有证据就全是 0（中性）。"""
        ev = evidence or {}
        hb = {name: 0.0 for name in HORMONES}
        db = {dim: 0.0 for dim in DIM_LABELS}
        why: list[str] = []

        debt = float(ev.get("sleep_debt") or self.state.get("sleep_debt") or 0.0)
        if debt >= 6.0:
            hb["melatonin"] += 0.05
            hb["cortisol"] += 0.03
            hb["dopamine"] -= 0.03
            db["fatigue"] += 0.06
            db["arousal"] -= 0.04
            why.append(f"睡眠债 {debt:.1f} 小时 → 困、唤醒低")

        sent = ev.get("sentiment")
        samples = int(ev.get("samples") or 0)
        if sent is not None and samples >= 5:
            if sent >= 0.20:
                hb["oxytocin"] += 0.04
                hb["serotonin"] += 0.03
                db["affiliation"] += 0.05
                db["valence"] += 0.03
                why.append(f"最近和对面相处 {sent:+.2f}（{samples} 条）→ 亲近、血清素偏高")
            elif sent <= -0.20:
                hb["cortisol"] += 0.04
                hb["serotonin"] -= 0.03
                db["valence"] -= 0.04
                db["tension"] += 0.04
                why.append(f"最近和对面相处 {sent:+.2f}（{samples} 条）→ 绷着、愉悦偏低")

        days = ev.get("days_since_active")
        if days is not None and float(days) >= 3.0:
            hb["oxytocin"] -= 0.03
            db["affiliation"] -= 0.04
            why.append(f"{float(days):.0f} 天没人说话 → 亲近感偏低")

        neg_until = float(self.state.get("negative_until") or 0.0)
        if neg_until > time.time():
            hb["cortisol"] += 0.04
            hb["serotonin"] -= 0.03
            db["valence"] -= 0.04
            db["tension"] += 0.04
            why.append("昨天那次不愉快还没走完 → 皮质醇偏高")

        app = self.state.get("last_appraisal") or {}
        if app and str(app.get("kind")) == "praise":
            if time.time() - float(app.get("ts") or 0.0) < 86400:
                hb["dopamine"] += 0.03
                db["valence"] += 0.03
                why.append("24 小时内被夸过 → 多巴胺偏高")

        hb = {name: self._dead(v) for name, v in hb.items()}
        db = {dim: self._dead(v, 0.02, 0.10) for dim, v in db.items()}
        return hb, db, why

    def new_day(self, today: str, evidence: dict | None = None) -> None:
        # 昼夜形状是生理，不是情绪：固定用配置里的中点，不再随机抖动
        params = {}
        for name, spec in HORMONES.items():
            params[name] = {
                "peak": spec["peak"],
                "width": (self.width_min + self.width_max) / 2.0,
                "scale": (self.amp_min + self.amp_max) / 2.0,
            }
        ev = evidence
        if ev is None and callable(getattr(self, "evidence_provider", None)):
            try:
                ev = self.evidence_provider()
            except Exception:  # noqa: BLE001
                ev = None
        bias, mood_bias, why = self.derive_day(ev)
        keep = {
            key: self.state.get(key)
            for key in (
                "last_card",
                "card_count",
                "last_comfort_ts",
                "active_qq",
                "profiles_meta",
                "sleep_debt",
                "last_appraisal",
                "negative_until",
            )
            if self.state.get(key) is not None
        }
        self.state.clear()
        self.state.update(
            {
                "day": today,
                "ts": time.time(),
                "bias": bias,
                "day_params": params,
                "mood_bias": mood_bias,
                "mood_reasons": why,
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
        if not self.random_event_enabled:
            return
        for name in random.sample(list(HORMONES), random.randint(1, 2)):
            delta = random.uniform(0.03, 0.07) * random.choice((-1, 1))
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
        hour = self.hour_now()
        out = {}
        for dim, weights in DIMS.items():
            # 情绪只看「偏离此刻应有水平」的部分：几点钟本身不该算情绪
            raw = sum(
                w * (float(h.get(name, HORMONES[name]["mean"])) - self.circadian(name, hour))
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

    @staticmethod
    def _proto_dims(proto: tuple) -> tuple:
        v, a, d, af, c = proto[:5]
        tension = max(-1.0, min(1.0, 0.70 * a - 0.60 * v))
        fatigue = max(-1.0, min(1.0, -0.80 * a - 0.20 * v))
        immersion = max(-1.0, min(1.0, 0.50 * a + 0.30 * c - 0.10 * abs(v)))
        return (v, a, d, af, c, tension, fatigue, immersion)

    @staticmethod
    def _vec(dims: dict) -> list:
        return [float(dims.get(k, 0.0)) for k in DIM_LABELS]

    @staticmethod
    def _dot(x: list, y: list) -> float:
        return sum(a * b for a, b in zip(x, y))

    @staticmethod
    def _norm(x: list) -> float:
        return math.sqrt(sum(a * a for a in x))

    def _rank(self, vec: list) -> list:
        """按方向相似度排序（余弦），返回 [(cos, name, |proto|)]。"""
        out = []
        nv = self._norm(vec) or 1e-6
        for name, proto in EMOTIONS.items():
            pv = list(self._proto_dims(proto))
            npv = self._norm(pv) or 1e-6
            cos = self._dot(vec, pv) / (nv * npv)
            out.append((cos, name, npv))
        out.sort(key=lambda x: -x[0])
        return out

    @staticmethod
    def _level(intensity: float) -> str:
        if intensity >= 0.72:
            return "强"
        if intensity >= 0.42:
            return "中"
        return "轻"

    def _ema(self, key: str, vec: list, now: float, tau: float, boost: float = 0.0) -> list:
        """把八维按时间常数做指数平滑；状态驱动得慢，社交冲击过得快。"""
        prev = self.state.get(key)
        prev_ts = self.state.get(key + "_ts")
        if not prev or not prev_ts:
            self.state[key] = list(vec)
            self.state[key + "_ts"] = now
            return list(vec)
        dt = max(0.0, now - float(prev_ts))
        alpha = 1.0 - math.exp(-dt / max(1.0, tau))
        # 变化越猛，越允许它快一点过去；但仍然不是瞬移
        if boost:
            shock = sum(abs(float(v) - float(p)) for p, v in zip(prev, vec)) / len(vec)
            alpha = min(1.0, alpha + boost * min(1.0, shock / 0.5))
        out = [float(p) + (float(v) - float(p)) * alpha for p, v in zip(prev, vec)]
        self.state[key] = out
        self.state[key + "_ts"] = now
        return out

    def affect_vec(self, dims: dict | None = None) -> tuple:
        """返回（当下, 基调, 是否突变）：慢事件平滑走，突变直接过，基调始终慢。"""
        dims = dims or self.dims()
        now = time.time()
        raw = self._vec(dims)
        prev_raw = self.state.get("dims_raw")
        prev_ts = float(self.state.get("dims_raw_ts") or 0.0)
        shock = 0.0
        if prev_raw and prev_ts:
            dt = max(0.0, now - prev_ts)
            # 取单维最大跳变：八维平均会把「一句话被狠狠戳到」稀释掉
            gap = max(abs(float(v) - float(p)) for p, v in zip(prev_raw, raw))
            # 短时间内的大跳才算冲击；慢慢漂出来的不算
            shock = gap if dt <= 90 else gap * (90.0 / dt)
        self.state["dims_raw"] = list(raw)
        self.state["dims_raw_ts"] = now

        burst = shock >= self.burst_threshold
        if burst:
            # 记下来，接下来这段时间（默认 25 秒）都算突变，别第二句又滑回去
            self.state["emotion_burst"] = {"kind": "shock", "ts": now, "strength": min(1.0, shock)}
        marker = self.state.get("emotion_burst") or {}
        if marker and (now - float(marker.get("ts") or 0.0)) <= self.burst_seconds:
            burst = True

        if burst:
            fast = list(raw)          # 突变不走平滑，该跳就跳
        else:
            fast = self._ema("dims_fast", raw, now, self.smooth_seconds, boost=0.35)
        slow = self._ema("dims_mood", raw, now, self.mood_seconds, boost=0.04)
        mixed = [0.65 * f + 0.35 * s for f, s in zip(fast, slow)]
        return mixed, slow, burst

    def mood_text(self, dims: dict | None = None) -> str:
        """慢层基调：不跟着一句话跳，用来描述「最近这段时间」。"""
        dims = dims or self.dims()
        _, slow, _burst = self.affect_vec(dims)
        v, a, d, af, c = slow[0], slow[1], slow[2], slow[3], slow[4]
        ten, fat = slow[5], slow[6]
        if fat > 0.35:
            return "有点乏"
        if ten > 0.35 and v < -0.15:
            return "绷着"
        if v > 0.30 and a > 0.15:
            return "偏亮"
        if v > 0.20:
            return "偏暖"
        if v < -0.30:
            return "偏沉"
        if af > 0.30:
            return "想亲近"
        if c < -0.20:
            return "有点没底"
        return "平稳"

    def emotion_detail(self, dims: dict | None = None) -> dict:
        """主情绪 + 强度 + 等级 + 次情绪 + 过渡/余味；快慢两层平滑，不一句话跳脸。"""
        dims = dims or self.dims()
        vec, slow, burst = self.affect_vec(dims)
        magnitude = self._norm(vec)
        now = time.time()

        if magnitude < 0.22:
            ranked = [(1.0, "平静", 0.5)]
            best, best_cos, second, second_cos = "平静", 1.0, "", -1.0
        else:
            ranked = self._rank(vec)
            best_cos, best = ranked[0][0], ranked[0][1]
            second_cos, second = (ranked[1][0], ranked[1][1]) if len(ranked) > 1 else (-1.0, "")

        prev = str(self.state.get("emotion_now") or "")
        since = float(self.state.get("emotion_since") or 0.0)
        if prev and prev != best and prev in EMOTIONS and magnitude >= 0.22 and not burst:
            prev_cos = dict((n, c) for c, n, _ in ranked).get(prev, -1.0)
            if (prev_cos - best_cos) > -0.10 and (now - since) < self.dwell_seconds:
                best, second = prev, (best if second_cos < best_cos else second)

        cos_fit = max(0.0, min(1.0, (best_cos + 1.0) / 2.0))
        intensity = max(0.0, min(1.0, (magnitude / 1.25) * (0.45 + 0.55 * cos_fit)))
        if best == "平静" and magnitude < 0.22:
            intensity = min(intensity, 0.35)
        if burst:
            intensity = max(0.0, min(1.0, intensity * 1.15))

        # 换情绪：记一条过渡，强度先低后高，别瞬移
        trans = self.state.get("emotion_transition") or {}
        if prev and prev != best and prev in EMOTIONS:
            self.state["emotion_aftertaste"] = {
                "name": prev,
                "ts": now,
                "intensity": float((self.state.get("emotion_aftertaste") or {}).get("intensity") or intensity),
            }
            self.state["emotion_transition"] = {"from": prev, "to": best, "ts": now}
            self.state["emotion_since"] = now
            trans = self.state["emotion_transition"]
        self.state["emotion_now"] = best
        if not self.state.get("emotion_since"):
            self.state["emotion_since"] = now

        progress = 1.0
        if trans and str(trans.get("to")) == best and self.ramp_seconds > 0 and not burst:
            progress = max(0.0, min(1.0, (now - float(trans.get("ts") or 0.0)) / self.ramp_seconds))
            intensity *= 0.55 + 0.45 * progress

        after = self.state.get("emotion_aftertaste") or {}
        aftertaste, after_strength = "", 0.0
        if after and self.aftertaste_minutes:
            age = now - float(after.get("ts") or 0.0)
            ttl = self.aftertaste_minutes * 60.0
            if 0 <= age < ttl and str(after.get("name")) in EMOTIONS and str(after.get("name")) != best:
                aftertaste = str(after.get("name"))
                after_strength = max(0.0, 1.0 - age / ttl)

        compound = ""
        if second and second != best and magnitude >= 0.30:
            if (best_cos - second_cos) < self.blend_gap:
                compound = second

        self._last_dims = dict(dims)
        self._last_emotion = best
        return {
            "name": best,
            "intensity": intensity,
            "level": self._level(intensity),
            "second": compound,
            "aftertaste": aftertaste,
            "aftertaste_strength": after_strength,
            "transition_from": str(trans.get("from") or "") if progress < 1.0 else "",
            "burst": burst,
            "transition_progress": progress,
            "magnitude": magnitude,
            "mood": self.mood_text(dims),
            "since": float(self.state.get("emotion_since") or now),
        }

    def emotion(self, dims: dict | None = None) -> str:
        """兼容旧接口：只返回主情绪名。"""
        return str(self.emotion_detail(dims)["name"])

    def emotion_text(self, dims: dict | None = None) -> str:
        """给注入用的一句话：从委屈往平静走（中），余味：害怕"""
        d = self.emotion_detail(dims)
        src = str(d.get("transition_from") or "")
        if d.get("burst"):
            text = f"突然{d['name']}（{d['level']}"
            if d["second"]:
                text += f"，带点{d['second']}"
            return text + "）"
        if src and d.get("transition_progress", 1.0) < 1.0:
            text = f"正从{src}往{d['name']}走（{d['level']}"
        else:
            text = f"{d['name']}（{d['level']}"
        if d["second"]:
            text += f"，带点{d['second']}"
        text += "）"
        if d["aftertaste"] and not src:
            text += f"，余味：{d['aftertaste']}"
        return text

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
