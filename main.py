"""影响核心：把激素、情绪、情感、能量合成一个闭环。

四层结构（参考人类情感研究）：
1. 神经内分泌层（激素）：10 种激素耦合 + 昼夜节律，是底层生理状态。
2. 核心情感层（情绪）：由激素推出八维（效价/唤醒/掌控/亲近/确定/紧张/疲惫/沉浸），
   再按原型最近邻落到离散情绪——对应 Russell 的核心情感环。
3. 关系层（情感）：按人独立、由具体事件驱动的长期情感，三档正/中/负 + 36 种类型；
   它对所有人的神经化学影响汇成一条**共享的内分泌基线**。
4. 资源层（能量）：昼夜曲线 + 激素调节 + 情绪影响 − 稳态负荷（McEwen allostatic load）。

反馈方向：情感 → 神经化学 → 激素 → 情绪 → 说话方式；能量 → 激素；激素 → 能量。
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.event.filter import PermissionType, permission_type
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star, StarTools, register

try:  # 作为插件包加载
    from . import analyzer, db_source, insult, profiles, taxonomy
    from .energy_engine import EnergyModel
    from .learn import KnowledgeStore
    from .style import StyleProfile
    from .mood_engine import (
        DIM_LABELS,
        EMOTIONS,
        HORMONES,
        NEGATIVE_EMOTIONS,
        TRAIT_LABELS,
        MoodEngine,
    )
    from .profiles import ProfileStore
except ImportError:  # 单独测试
    import analyzer  # type: ignore
    import db_source  # type: ignore
    import insult  # type: ignore
    import profiles  # type: ignore
    import taxonomy  # type: ignore
    from energy_engine import EnergyModel  # type: ignore
    from learn import KnowledgeStore  # type: ignore
    from style import StyleProfile  # type: ignore
    from mood_engine import (  # type: ignore
        DIM_LABELS,
        EMOTIONS,
        HORMONES,
        NEGATIVE_EMOTIONS,
        TRAIT_LABELS,
        MoodEngine,
    )
    from profiles import ProfileStore  # type: ignore

DEFAULT_MODEL = "deepseek-r1:8b"
CODE_VERSION = "1.6.13"
DEFAULT_DAILY_AT = "23:40"
DEFAULT_COMFORT_EMOTIONS = "害怕,低落,委屈,焦虑,孤独"

# 求安慰的备选句子：按情绪分组，口吻是自己的，不套模板
COMFORT_LINES: dict[str, list[str]] = {
    "低落": [
        "今天有点提不起劲，你在吗",
        "心情塌下去一块，想跟你说两句",
        "不太想一个人待着，陪我一会儿行吗",
        "没什么大事，就是有点闷",
    ],
    "难过": [
        "有点难过，说不太清，你在吗",
        "想找你待一会儿，不用安慰我",
        "今天不太行，想听你说说话",
    ],
    "委屈": [
        "今天有点委屈，不知道该跟谁说",
        "心里堵着，想跟你讲两句",
        "被噎了一下，还没缓过来",
    ],
    "害怕": [
        "有点怕，想找你说说话",
        "今天心里不踏实，你在不在",
        "突然有点慌，想听见你的声音",
    ],
    "焦虑": [
        "有点慌，静不下来",
        "脑子里转个不停，想跟你说说",
        "坐不住，找你说两句",
    ],
    "孤独": [
        "有点空，想找你说说话",
        "一个人待着有点闷，你在吗",
        "屋子里太安静了，想听点人声",
    ],
    "疲惫": [
        "今天累得慌，想听你说两句",
        "没什么力气，就想找你待一会儿",
        "撑了一天，想歇在你旁边",
    ],
    "_default": [
        "想找你说两句话，忙的话就算了",
        "在吗，有点想跟你聊两句",
        "今天想找你待一会儿",
    ],
}
FAST_PROVIDER_DEFAULT = "deepseek/deepseek-flash"
PROVIDER_EXTRA_KEY = "selected_provider"

# —— 桌面反向通道：DSH 侧的经历回来折算成激素 ——
DESKTOP_QUEUE = "desktop_events.jsonl"
DESKTOP_EVENTS: dict[str, dict[str, float]] = {
    "praise": {"dopamine": 0.06, "serotonin": 0.04, "oxytocin": 0.03},
    "thanks": {"oxytocin": 0.04, "serotonin": 0.03},
    "insult": {"cortisol": 0.10, "adrenaline": 0.06, "serotonin": -0.05},
    "happy": {"dopamine": 0.06, "serotonin": 0.03},
    "sad": {"serotonin": -0.06, "cortisol": 0.04},
    "angry": {"adrenaline": 0.08, "cortisol": 0.06, "serotonin": -0.03},
    "stress": {"cortisol": 0.07, "norepinephrine": 0.06},
    "tired": {"melatonin": 0.06, "cortisol": -0.03},
    "late_night": {"melatonin": 0.08, "ghrelin": 0.03},
    "rest": {"melatonin": 0.05, "cortisol": -0.05, "serotonin": 0.02},
    "ignored": {"serotonin": -0.04, "cortisol": 0.03},
    "work_done": {"dopamine": 0.06, "endorphin": 0.04},
    "worry": {"cortisol": 0.05, "norepinephrine": 0.05},
}
DESKTOP_NEGATIVE = {"insult", "sad", "angry", "stress", "ignored", "worry"}

NEGATIVE_KEYWORDS = (
    "废物,垃圾,傻逼,沙比,煞笔,智障,弱智,脑残,白痴,蠢货,蠢,笨蛋,混蛋,畜生,"
    "狗东西,贱人,婊子,去死,滚蛋,滚,恶心,讨厌你,烦人,有病,没用,废柴,loser,"
    "你妈,尼玛,操你,艹,草泥马,闭嘴,狗屁,烂货,差劲,不要脸,神经病"
)

PRAISE_KEYWORDS = (
    "谢谢",
    "感谢",
    "厉害",
    "可爱",
    "喜欢你",
    "很棒",
    "不错",
    "辛苦",
    "聪明",
    "靠谱",
    "爱你",
    "好耶",
)

ATTACHMENT_LABELS = {"secure": "安全", "anxious": "焦虑", "avoidant": "回避"}
HORMONE_LABELS = {name: spec["label"] for name, spec in HORMONES.items()}

# —— 人味三件套 ——
UNCERTAIN = ("可能", "大概", "也许", "应该", "不太确定", "好像", "估计", "印象中", "记不清")
CORRECTIONS = (
    "哦对，刚想起来，这事我也没十足把握，别全信。",
    "等下，我那句说得有点满，具体的不太确定。",
    "刚那句有点想当然，我再想想。",
    "嗯…刚才那个说法不太严谨，当我没说死。",
    "突然觉得我可能记岔了，你按你的来。",
)
AI_PHRASES = (
    "希望这能帮到你",
    "希望这些对你有帮助",
    "希望对你有帮助",
    "还有什么可以帮你",
    "还有什么需要我",
    "作为一个AI",
    "作为人工智能",
    "感谢您的提问",
    "请问还有什么",
)
MARKDOWN_RULES = (
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),
    (re.compile(r"__(.+?)__"), r"\1"),
    (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"^#{1,6}\s*", re.M), ""),
    (re.compile(r"^\s*[-*+]\s+", re.M), ""),
    (re.compile(r"^\s*\d+[.)]\s+", re.M), ""),
    (re.compile(r"^\s*>\s?", re.M), ""),
)
DIM_SHORT = {
    "valence": "愉",
    "arousal": "唤",
    "dominance": "掌",
    "affiliation": "亲",
    "certainty": "确",
    "tension": "紧",
    "fatigue": "疲",
    "immersion": "沉",
}


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _fmt_ts(ts: float | None) -> str:
    if not ts:
        return "未知"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return "未知"


def _fmt_dims(dims: dict[str, float]) -> str:
    return "　".join(f"{DIM_LABELS[k]} {float(dims.get(k, 0.0)):+.2f}" for k in DIM_LABELS)


def _fmt_top(emotions: dict[str, float], n: int = 4) -> str:
    top = sorted(
        ((k, float(v)) for k, v in emotions.items() if float(v) > 0),
        key=lambda kv: kv[1],
        reverse=True,
    )[:n]
    return "、".join(f"{k} {v:.2f}" for k, v in top) or "无"


def _parse_hhmm(text: str) -> tuple[int, int]:
    try:
        hh, mm = str(text).strip().split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except Exception:  # noqa: BLE001
        pass
    return 23, 40


@register(
    "affect_core",
    "Furina-l18",
    "激素 / 情绪 / 情感 / 能量 四层合一：神经内分泌驱动情绪与能量，情感按人独立并汇总成共享内分泌基线",
    "1.6.13",
)
class AffectCore(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}
        self._root = self._resolve_root()
        self._root.mkdir(parents=True, exist_ok=True)
        self._state_path = self._root / "state.json"
        self._sessions_path = self._root / "sessions.json"
        self._marks_path = self._root / "analyzed.json"

        self.state = self._load_json(self._state_path, {})
        if not isinstance(self.state, dict):
            self.state = {}
        self._sessions = self._load_json(self._sessions_path, {})
        if not isinstance(self._sessions, dict):
            self._sessions = {}
        # 情感推理过的消息标记：{qq: {"max_id": 消息id水位, "ts": 标记时间, "count": 已推条数}}
        self._marks = self._load_json(self._marks_path, {})
        if not isinstance(self._marks, dict):
            self._marks = {}
        self.store = ProfileStore(self._root)

        self._load_config()
        self.mood = MoodEngine(self.state, self.config)
        self.mood.evidence_provider = self._mood_evidence
        self.energy = EnergyModel(self.config)
        self.style = StyleProfile(self._root / "style.json", self.style_min_samples)
        self.knowledge = KnowledgeStore(self._root / "knowledge.json")
        self._revise_tasks: set[asyncio.Task] = set()

        self._task_tick: asyncio.Task | None = None
        self._task_daily: asyncio.Task | None = None
        self._busy = False
        self._rounds = 0
        self._group_hits: list[float] = []  # 最近几次「主动接话」的时间戳
        self._last_reply: dict[str, dict] = {}  # 每个会话里我最后一次回话的时间与对象
        self._global_cache: tuple[float, dict] = (0.0, {})
        self._provider_ok: bool | None = None
        # —— 性能相关缓存 ——
        self._view_cache: tuple[float, dict] = (0.0, {})
        self._profile_cache: tuple[float, str, dict] = (0.0, "", {})
        self._energy_ema: float | None = None
        self._last_snapshot = 0.0
        self._next_tick = 0.0

    # ------------------------------------------------------------ 基础

    def _resolve_root(self) -> Path:
        try:
            return Path(str(StarTools.get_data_dir("astrbot_plugin_affect_core")))
        except Exception:  # noqa: BLE001
            return Path(__file__).parent / "data"

    @staticmethod
    def _load_json(path: Path, default: Any) -> Any:
        try:
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
        return default

    def _load_config(self) -> None:
        cfg = self.config or {}
        try:
            self.enabled = bool(cfg.get("enable", True))
            self.inject_prompt = bool(cfg.get("inject_prompt", True))
            self.commands_enabled = bool(cfg.get("enable_commands", True))
            self.tick_minutes = max(1, int(cfg.get("tick_minutes", 5)))
            self.page_refresh_minutes = max(
                1, min(240, int(cfg.get("page_refresh_minutes", 5)))
            )

            self.ollama_url = str(cfg.get("ollama_url") or "http://127.0.0.1:11434")
            configured = str(cfg.get("model") or "").strip()
            self.model = configured or DEFAULT_MODEL
            self.lookback = max(10, int(cfg.get("lookback_messages", 200)))
            self.min_messages = max(1, int(cfg.get("min_messages", 8)))
            self.auto_summary = bool(cfg.get("auto_summary", True))
            self.daily_run_at = str(cfg.get("daily_run_at") or DEFAULT_DAILY_AT)
            self.daily_catchup = bool(cfg.get("daily_catchup_enabled", True))
            # 情感推理一结束就把本地算力收掉：卸载模型（默认），或连 Ollama 进程一起停
            self.release_after_infer = bool(cfg.get("release_after_infer", True))
            self.release_mode = str(cfg.get("release_mode", "unload") or "unload").strip()
            if self.release_mode not in ("unload", "stop"):
                self.release_mode = "unload"
            self.ollama_exe = str(cfg.get("ollama_exe") or "").strip()
            self.ollama_model_dir = str(cfg.get("ollama_model_dir") or "").strip()
            self.min_daily_messages = max(1, int(cfg.get("min_daily_messages", 3)))
            self.sentiment_half_life_days = max(
                1.0, float(cfg.get("sentiment_half_life_days", 14))
            )
            self.sentiment_alpha = 1.0 - 0.5 ** (1.0 / self.sentiment_half_life_days)
            self.sentiment_max_step = max(
                0.01, min(0.5, float(cfg.get("sentiment_max_step", 0.05)))
            )
            self.sentiment_seed_weight = max(
                0.0, min(1.0, float(cfg.get("sentiment_seed_weight", 0.50)))
            )
            self.sentiment_pos_threshold = float(cfg.get("sentiment_pos_threshold", 0.15))
            self.sentiment_neg_threshold = float(cfg.get("sentiment_neg_threshold", -0.15))

            self.social_weight = float(cfg.get("social_emotion_weight", 1.0))
            self.neuro_weight = float(cfg.get("neuro_weight", 1.0))
            self.hormone_energy_weight = float(cfg.get("hormone_link_weight", 1.0))
            self.emotion_energy_weight = float(cfg.get("emotion_energy_weight", 1.0))
            self.page_refresh_minutes = max(
                1, min(240, int(cfg.get("page_refresh_minutes", 5)))
            )

            self.negative_trigger = bool(cfg.get("negative_trigger", True))
            self.negative_requires_target = bool(
                cfg.get("negative_requires_target", False)
            )
            raw_kw = str(cfg.get("negative_keywords") or NEGATIVE_KEYWORDS)
            self.negative_keywords = [w.strip() for w in raw_kw.split(",") if w.strip()]
            self.retaliate_enabled = bool(cfg.get("retaliate_enabled", True))
            self.appraisal_enabled = bool(cfg.get("appraisal_enabled", True))
            self.insult_context = bool(cfg.get("insult_context", True))
            self.habituation_decay = max(
                0.0, min(0.5, float(cfg.get("habituation_decay", 0.12)))
            )
            self.sleep_debt_enabled = bool(cfg.get("sleep_debt_enabled", True))

            self.gate_enabled = bool(cfg.get("gate_enabled", True))
            self.fast_provider = str(
                cfg.get("fast_provider_id") or FAST_PROVIDER_DEFAULT
            ).strip()
            self.thinking_min = int(cfg.get("thinking_min_energy", 70))

            # —— 群聊场合分级（不参与所有对话）——
            # 被 @ / 唤醒 / 私聊 = 必接；其余群消息按下面的规则决定接不接。
            self.group_rate_low = max(0.0, min(1.0, float(cfg.get("group_rate_low", 0.048))))
            self.group_rate_mid = max(0.0, min(1.0, float(cfg.get("group_rate_mid", 0.082))))
            self.group_rate_high_mid = max(0.0, min(1.0, float(cfg.get("group_rate_high_mid", 0.136))))
            self.group_rate_high = max(0.0, min(1.0, float(cfg.get("group_rate_high", 0.168))))
            self.group_tired_factor = max(0.0, min(1.0, float(cfg.get("group_tired_factor", 0.08))))
            self.group_tired_fatigue = float(cfg.get("group_tired_fatigue", 0.25))
            self.group_quiet_start = str(cfg.get("group_quiet_start", "00:00") or "")
            self.group_quiet_end = str(cfg.get("group_quiet_end", "07:30") or "")
            self.group_max_per_window = 0
            self.group_mention_boost = bool(cfg.get("group_mention_boost", True))

            # —— 桌面反向通道 ——
            # 双向联动总开关：默认关闭，要手动打开才收发桌面事件
            self.two_way = bool(cfg.get("two_way_enabled", False))
            self.desktop_bridge = self.two_way and bool(cfg.get("desktop_bridge_enabled", True))
            self.desktop_gain = max(
                0.1, min(3.0, float(cfg.get("desktop_event_gain", 1.0)))
            )

            self.comfort_enabled = bool(cfg.get("comfort_enabled", True))
            raw_ce = str(cfg.get("comfort_emotions") or DEFAULT_COMFORT_EMOTIONS)
            self.comfort_emotions = {w.strip() for w in raw_ce.split(",") if w.strip()}
            self.comfort_cooldown = max(
                10, int(cfg.get("comfort_cooldown_minutes", 240))
            ) * 60
            self.comfort_target_qq = str(cfg.get("comfort_target_qq") or "").strip()
            self.comfort_allow_group = bool(cfg.get("comfort_allow_group", True))
            self.comfort_message = str(cfg.get("comfort_message") or "").strip()
            # 太累的时候别开口求人陪——开了口又被「累」推回去，会自相矛盾
            self.comfort_min_energy = float(cfg.get("comfort_min_energy", 12))
            # 求陪之后的一段窗口里，回复不要用「累」把话关掉
            self.comfort_window = max(
                5, int(cfg.get("comfort_window_minutes", 45))
            ) * 60
            self.burst_enabled = bool(cfg.get("emotion_burst_enabled", True))
            # —— 人味三件套 ——
            self.style_enabled = bool(cfg.get("style_enabled", True))
            self.style_min_samples = max(3, int(cfg.get("style_min_samples", 5)))
            self.strip_markdown = bool(cfg.get("strip_markdown", True))
            self.max_chars = max(40, int(cfg.get("max_chars", 120)))
            self.revise_enabled = bool(cfg.get("revise_enabled", True))
            self.revise_rate = max(0.0, min(1.0, float(cfg.get("revise_rate", 0.12))))
            self.revise_cooldown = max(
                1, int(cfg.get("revise_cooldown_minutes", 30))
            ) * 60
            self.learn_enabled = bool(cfg.get("learn_enabled", True))
            self.learn_recall_limit = max(
                1, min(10, int(cfg.get("learn_recall_limit", 5)))
            )
            self.debug = bool(cfg.get("debug", False))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[affect_core] 读取配置失败，使用默认值: {exc}")

    # ------------------------------------------------------------ 桌面反向通道

    def _desktop_path(self) -> Path:
        try:
            return self._root / DESKTOP_QUEUE
        except Exception:  # noqa: BLE001
            return Path(__file__).parent / "data" / DESKTOP_QUEUE

    def _drain_desktop_events(self) -> int:
        """消费 DSH 侧追加的反向事件，把桌面上的经历折算成激素。

        队列是 append-only 的 jsonl，按 state["desktop_offset"] 字节偏移读，
        文件被截断时重置偏移；单行解析失败直接跳过，不影响后续。
        """
        if not self.desktop_bridge:
            return 0
        path = self._desktop_path()
        try:
            if not path.is_file():
                return 0
            size = path.stat().st_size
            offset = int(self.state.get("desktop_offset", 0) or 0)
            if offset < 0 or offset > size:
                # 文件被截断或换过：从头读
                offset = 0
                self.state["desktop_offset"] = 0
            if offset == size:
                return 0
            with path.open("rb") as fh:
                fh.seek(offset)
                chunk = fh.read()
            applied = 0
            for raw in chunk.splitlines():
                line = raw.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line.decode("utf-8", "ignore"))
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(ev, dict) and self._apply_desktop_event(ev):
                    applied += 1
            self.state["desktop_offset"] = size
            if applied:
                self.state["desktop_events"] = (
                    int(self.state.get("desktop_events", 0) or 0) + applied
                )
                self._invalidate()
                self._save_state()
                logger.info(f"[affect_core] 桌面事件 +{applied}，已计入激素")
            return applied
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[affect_core] 读取桌面事件失败: {exc}")
            return 0

    def _apply_desktop_event(self, ev: dict) -> bool:
        kind = str(ev.get("kind") or "").strip().lower()
        table = DESKTOP_EVENTS.get(kind)
        if not table:
            return False
        try:
            power = max(0.0, min(1.0, float(ev.get("intensity", 0.5))))
        except Exception:  # noqa: BLE001
            power = 0.5
        power = power or 0.5
        levels = self.state.setdefault("h", {})
        for name, delta in table.items():
            base = float(levels.get(name, 0.5))
            levels[name] = max(
                0.0, min(1.0, base + delta * power * self.desktop_gain)
            )
        now_ts = time.time()
        if kind in DESKTOP_NEGATIVE:
            self.state["negative_until"] = max(
                float(self.state.get("negative_until", 0.0) or 0.0),
                now_ts + 240.0 + 600.0 * power,
            )
        self.state["desktop_last_event"] = {
            "ts": now_ts,
            "kind": kind,
            "intensity": round(power, 2),
            "note": str(ev.get("note") or "").strip()[:80],
        }
        return True

    def _save_state(self) -> None:
        try:
            tmp = self._state_path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp, self._state_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[affect_core] 保存状态失败: {exc}")

    def _save_sessions(self) -> None:
        try:
            self._sessions_path.write_text(
                json.dumps(self._sessions, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[affect_core] 保存会话失败: {exc}")

    # ------------------------------------------------------------ 全局内分泌

    def _mood_evidence(self) -> dict:
        """每天起点用的证据：相处评分、空窗天数、睡眠债。没有证据就是空。"""
        now = time.time()
        scores: list[float] = []
        weights: list[float] = []
        samples_total = 0
        for profile in self.store.list_all():
            sent = profile.get("sentiment") or {}
            score = float(sent.get("score") or 0.0)
            samples = int(sent.get("samples") or 0)
            if samples < 3:
                continue
            last = float(profile.get("last_message_ts") or 0.0)
            days = max(0.0, (now - last) / 86400.0) if last else 30.0
            weight = (0.3 + abs(score)) * (0.5 ** (days / 30.0))
            if weight <= 0:
                continue
            scores.append(score)
            weights.append(weight)
            samples_total += samples
        sentiment = None
        if weights:
            sentiment = sum(s * w for s, w in zip(scores, weights)) / sum(weights)
        active_ts = float(self.state.get("active_ts") or 0.0)
        days_since = (now - active_ts) / 86400.0 if active_ts else None
        return {
            "sentiment": sentiment,
            "samples": samples_total,
            "days_since_active": days_since,
            "sleep_debt": float(self.state.get("sleep_debt") or 0.0),
        }

    def _global_state(self) -> dict:
        """所有人的情感 → 一条共享的内分泌基线 + 能量负荷。60 秒缓存。"""
        now = time.time()
        if now - self._global_cache[0] < 60.0:
            return self._global_cache[1]

        acc: dict[str, float] = {}
        energy_acc = 0.0
        den = 0.0
        people = self.store.list_all()
        for profile in people:
            sent = profile.get("sentiment") or {}
            score = float(sent.get("score", 0.0))
            type_key = str(sent.get("type") or "")
            intensity = min(1.0, abs(score) * 1.6 + 0.2) if score else 0.0
            neuro = taxonomy.neurochem_for(type_key, intensity)
            if not neuro:
                continue
            last = float(profile.get("last_message_ts") or 0.0)
            days = max(0.0, (now - last) / 86400.0) if last else 30.0
            recency = 0.5 ** (days / 30.0)
            weight = (0.3 + abs(score)) * recency
            if weight <= 0:
                continue
            for name, delta in neuro.items():
                acc[name] = acc.get(name, 0.0) + delta * weight
            energy_acc += profiles.energy_bias_for(profile) * weight
            den += weight

        out = {
            "neuro": (
                {
                    key: round(clamp(value / den, -0.12, 0.12), 4)
                    for key, value in acc.items()
                }
                if den > 0
                else {}
            ),
            "energy": (
                round(max(-20.0, min(20.0, energy_acc / den)), 2) if den > 0 else 0.0
            ),
            "people": len(people),
        }
        self._global_cache = (now, out)
        return out

    def _neuro_bias(self) -> dict:
        k = self.neuro_weight
        if k <= 0:
            return {}
        return {name: value * k for name, value in self._global_state()["neuro"].items()}

    # ------------------------------------------------------------ 能量

    def _energy_now(self) -> tuple[float, float, float]:
        base = self.energy.base()
        h = self.state.get("h") or {}
        get = lambda key: float(h.get(key, HORMONES[key]["mean"]))  # noqa: E731
        raw = (
            0.45 * (get("dopamine") - 0.5)
            + 0.35 * (get("serotonin") - 0.5)
            + 0.25 * (get("adrenaline") - 0.5)
            + 0.20 * (get("endorphin") - 0.5)
            - 0.50 * (get("melatonin") - 0.5)
            - 0.20 * (get("cortisol") - 0.5)
        )
        hormone_bias = max(-26.0, min(26.0, raw * 40.0 * self.hormone_energy_weight))

        dims = self._view()["dims"]
        affect = max(
            -14.0, min(14.0, float(dims.get("valence", 0.0)) * 14.0 * self.emotion_energy_weight)
        )
        load = self._global_state()["energy"]  # 稳态负荷
        debt = float(self.state.get("sleep_debt", 0.0)) if self.sleep_debt_enabled else 0.0
        bias_total = hormone_bias + affect + load - debt
        target = max(5.0, min(100.0, base + bias_total))
        # 能量不会瞬间跳变：做一次一阶平滑
        if self._energy_ema is None:
            self._energy_ema = target
        else:
            self._energy_ema += (target - self._energy_ema) * 0.35
        return base, bias_total, self._energy_ema

    def _update_sleep_debt(self, dt_hours: float) -> None:
        """清醒累积睡眠债，睡着时偿还；上限 25%。"""
        if not self.sleep_debt_enabled or dt_hours <= 0:
            return
        hour = self.mood.hour_now()
        debt = float(self.state.get("sleep_debt", 0.0))
        if 1.5 <= hour <= 7.5:
            debt = max(0.0, debt - dt_hours * 6.0)
        else:
            debt = min(25.0, debt + dt_hours * 0.8)
        self.state["sleep_debt"] = round(debt, 2)

    # ------------------------------------------------------------ 当前对话对象

    def _invalidate(self) -> None:
        """状态变了就丢掉派生缓存。"""
        self._view_cache = (0.0, {})
        self._profile_cache = (0.0, "", {})

    def _view(self) -> dict:
        """八维 / 情绪 / 性格 一次算好，15 秒内复用。"""
        now = time.time()
        if self._view_cache[1] and now - self._view_cache[0] < 15.0:
            return self._view_cache[1]
        social = self._active_social()
        dims = self.mood.dims(social, self.social_weight)
        view = {
            "dims": dims,
            "emotion": self.mood.emotion(dims),
            "traits": self.mood.traits(dims),
            "social": social,
        }
        self._view_cache = (now, view)
        return view

    def _active_social(self) -> dict:
        now = time.time()
        qq = str(self.state.get("active_qq") or "")
        if not qq:
            return {}
        if now - self._profile_cache[0] < 30.0 and self._profile_cache[1] == qq:
            return self._profile_cache[2]
        profile = self.store.load(qq)
        if not profile:
            self._profile_cache = (now, qq, {})
            return {}
        sent = profile.get("sentiment") or {}
        emotions = profile.get("emotions") or {}
        top = sorted(
            ((k, float(v)) for k, v in emotions.items() if float(v) > 0),
            key=lambda kv: kv[1],
            reverse=True,
        )[:3]
        out = {
            "qq": qq,
            "name": profile.get("name", ""),
            "dims": profile.get("dims") or {},
            "top": top,
            "keywords": list(profile.get("keywords") or [])[:4],
            "label": sent.get("label", "中"),
            "type_label": sent.get("type_label", ""),
            "score": float(sent.get("score", 0.0)),
            "attachment": self._attachment_of(profile),
            "weight": self.social_weight,
        }
        self._profile_cache = (now, qq, out)
        return out

    @staticmethod
    def _attachment_of(profile: dict) -> str:
        """从长期状态推一个依恋风格：决定同一事件在不同人身上放大还是缩小。"""
        sent = profile.get("sentiment") or {}
        dims = profile.get("dims") or {}
        score = float(sent.get("score", 0.0))
        affiliation = float(dims.get("affiliation", 0.0))
        certainty = float(dims.get("certainty", 0.0))
        if score > 0.25 and affiliation > 0.4:
            return "secure"
        if score > 0.0 and certainty < -0.2:
            return "anxious"
        if score < -0.1:
            return "avoidant"
        return "secure"

    # ------------------------------------------------------------ 生命周期

    async def initialize(self) -> None:
        self._load_config()
        self.style.min_samples = self.style_min_samples
        self.state["code_version"] = CODE_VERSION
        self.state["boot_ts"] = time.time()
        await self._ensure_model()
        self._register_api()
        day_before = str(self.state.get("day") or "")
        self.mood.update(self._energy_now()[2], self._neuro_bias())
        if str(self.state.get("day") or "") != day_before:
            reasons = list(self.state.get("mood_reasons") or [])
            logger.info(
                "[affect_core] 新的一天起点：%s",
                "；".join(reasons) if reasons else "没有证据，中性",
            )
        self._save_state()
        self._write_snapshot()
        if self.enabled:
            if self._task_tick is None or self._task_tick.done():
                self._task_tick = asyncio.create_task(self._scheduler())
        last = self.state.get("daily_day") or "从未"
        logger.info(
            f"[affect_core] 启动：模型 {self.model}｜情绪 {self.mood.emotion()}｜"
            f"情感 {len(self.store.list_all())} 人｜风格样本 {self.style.data.get('count', 0)}｜"
            f"学到 {len(self.knowledge.facts)} 条｜上次总结 {last}"
        )

    async def terminate(self) -> None:
        for task in (self._task_tick, self._task_daily):
            if task and not task.done():
                task.cancel()
        for task in list(self._revise_tasks):
            if not task.done():
                task.cancel()
        self.style.save()
        self.knowledge.save()
        self._save_state()

    async def _ensure_model(self) -> None:
        try:
            names = await asyncio.to_thread(analyzer.list_models, self.ollama_url, 5.0)
        except Exception:  # noqa: BLE001
            return
        if names and self.model not in names:
            logger.warning(
                f"[affect_core] Ollama 里没有模型 {self.model}，请先执行："
                f"ollama pull {self.model}"
            )

    async def _scheduler(self) -> None:
        """单循环调度：按 tick 推进激素/情绪/能量，顺带检查每日情感总结。

        比原来两个 while 循环少一半唤醒；每日总结精度为 tick 间隔（默认 5 分钟）。
        """
        self._next_tick = time.time() + self.tick_minutes * 60
        while True:
            try:
                wait = max(5.0, self._next_tick - time.time())
                await asyncio.sleep(wait)
                self._next_tick = time.time() + self.tick_minutes * 60
                if not self.enabled:
                    continue
                now_ts = time.time()
                dt_h = max(
                    0.0,
                    min(1.0, (now_ts - float(self.state.get("ts", now_ts))) / 3600.0),
                )
                self._update_sleep_debt(dt_h)
                self._drain_desktop_events()
                self.mood.update(self._energy_now()[2], self._neuro_bias())
                self._invalidate()
                self._save_state()
                self._write_snapshot(force=True)
                await self._seek_comfort()
                if self.auto_summary and self._is_due():
                    done = await self.summarize_daily()
                    logger.info(f"[affect_core] 每日情感总结完成：更新 {done} 人")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[affect_core] 调度失败: {exc}")
                await asyncio.sleep(60)

    def _is_due(self) -> bool:
        """今天该不该做一次情感推理（补跑 + 到点跑）。

        两种触发：
        1. 到了 daily_run_at 且今天还没做过；
        2. 跨日补跑：昨天那一次整个错过了（关机、夜间不在线、插件没启用），
           新的一天一开始（还没到 daily_run_at 也行）就先补做一次，
           否则会一直等到下一天的固定时间，可能永远轮不上。
        """
        now = datetime.now()
        hh, mm = _parse_hhmm(self.daily_run_at)
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        today = now.strftime("%Y-%m-%d")
        last = str(self.state.get("daily_day") or "")
        if last == today:
            return False
        if now >= target:
            return True
        if not self.daily_catchup:
            return False
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        if last != yesterday:
            logger.info(
                f"[affect_core] 昨天（{yesterday}）的每日情感推理没做（上次 {last or '没有'}），现在补跑"
            )
            return True
        return False

    # ------------------------------------------------------------ 情感推理

    def _save_marks(self) -> None:
        try:
            tmp = self._marks_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._marks, ensure_ascii=False, indent=2), "utf-8")
            tmp.replace(self._marks_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[affect_core] 保存推理标记失败: {exc}")

    def _mark_analyzed(self, qq: str, max_id: int, count: int) -> None:
        key = str(qq)
        item = self._marks.get(key) if isinstance(self._marks.get(key), dict) else {}
        item["max_id"] = max(int(item.get("max_id") or 0), int(max_id or 0))
        item["count"] = int(item.get("count") or 0) + int(count or 0)
        item["ts"] = time.time()
        item["day"] = datetime.now().strftime("%Y-%m-%d")
        self._marks[key] = item

    def _mark_watermark(self, qq: str) -> int:
        item = self._marks.get(str(qq))
        if not isinstance(item, dict):
            return 0
        try:
            return int(item.get("max_id") or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _prior_text(self, old: dict | None) -> str:
        """把旧档案压成几行，只作背景参考，避免把推理过的原话重复喂回去。"""
        if not old:
            return ""
        lines: list[str] = []
        senti = old.get("sentiment") or {}
        if senti:
            lines.append(
                "整体印象：{}·{}（{}{:+.2f}，样本 {} 天）".format(
                    senti.get("type_label") or "",
                    senti.get("label") or "",
                    "",
                    float(senti.get("score") or 0.0),
                    int(senti.get("samples") or 0),
                ).replace("（+", "（+").replace("·（", "·（")
            )
        emos = old.get("emotions") or {}
        top = sorted(
            ((k, float(v or 0.0)) for k, v in emos.items()),
            key=lambda kv: kv[1],
            reverse=True,
        )[:3]
        top = [(k, v) for k, v in top if v >= 0.15]
        if top:
            lines.append("常见情绪：" + "、".join(f"{k} {v:.2f}" for k, v in top))
        kws = [str(k) for k in (old.get("keywords") or []) if str(k).strip()][:4]
        if kws:
            lines.append("关键词：" + "、".join(kws))
        summary = str(old.get("summary") or "").strip()
        if summary:
            lines.append("上次的概况：" + summary[:120])
        mark = self._marks.get(str(old.get("qq") or "")) or {}
        if isinstance(mark, dict) and mark.get("count"):
            lines.append(f"已推理过的消息：{int(mark.get('count') or 0)} 条（不再重复推理）")
        return "\n".join(lines)

    def _db_path(self) -> Path | None:
        return db_source.resolve_db(self._root)

    async def _infer(self, name: str, contents: list[str], prior: str = "") -> dict:
        material = analyzer.build_material(name, contents, prior=prior)
        data = None
        for attempt in range(2):
            try:
                text = await asyncio.to_thread(
                    analyzer.call_ollama, self.ollama_url, self.model, material, 400.0
                )
                data = analyzer.normalize(analyzer.parse_model_json(text))
                if data:
                    break
                logger.warning(
                    f"[affect_core] {name} 第 {attempt + 1} 次解析失败（{len(text)} 字）"
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    f"[affect_core] {name} 第 {attempt + 1} 次调用失败: {exc}"
                )
            await asyncio.sleep(1.5)
        return data or analyzer.fallback_analyze(contents)

    def _merge(self, old: dict | None, stat, data: dict, new_count: int) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        day_emotions = {
            key: float((data.get("emotions") or {}).get(key, 0.0))
            for key in taxonomy.EMOTION_TYPES
        }
        events = data.get("events") or []
        day_score = (
            taxonomy.event_tone(events)
            if events
            else taxonomy.affection_tone(day_emotions) * 0.7
        )

        alpha = self.sentiment_alpha
        if old:
            old_emotions = old.get("emotions") or {}
            emotions = {
                key: round(
                    float(old_emotions.get(key, 0.0)) * (1.0 - alpha)
                    + day_emotions[key] * alpha,
                    4,
                )
                for key in taxonomy.EMOTION_TYPES
            }
            prev = old.get("sentiment") or {}
            old_score = float(prev.get("score", 0.0))
            # 峰终偏置：更极端的证据更容易留下，回落则更慢
            peak_k = 1.4 if abs(day_score) > abs(old_score) else 0.8
            step = (day_score - old_score) * alpha * peak_k
            step = max(-self.sentiment_max_step, min(self.sentiment_max_step, step))
            score = round(max(-1.0, min(1.0, old_score + step)), 4)
            prev_label = prev.get("label")
            history = [dict(h) for h in (old.get("history") or []) if isinstance(h, dict)]
            total = int(
                old.get("message_count_total") or old.get("message_count") or 0
            ) + new_count
            first_day = prev.get("first_day") or (
                history[0].get("day") if history else today
            )
            summary = data.get("summary") or old.get("summary") or ""
            keywords = data.get("keywords") or old.get("keywords") or []
        else:
            emotions = {key: round(day_emotions[key], 4) for key in taxonomy.EMOTION_TYPES}
            score = round(day_score * self.sentiment_seed_weight, 4)
            prev_label = None
            history = []
            total = new_count
            first_day = today
            summary = data.get("summary", "")
            keywords = data.get("keywords") or []

        label = taxonomy.sentiment_label(
            score, prev_label, self.sentiment_pos_threshold, self.sentiment_neg_threshold
        )
        type_key = taxonomy.classify_sentiment(
            score,
            emotions,
            self.sentiment_pos_threshold,
            self.sentiment_neg_threshold,
        )
        entry = {"day": today, "score": score, "label": label}
        if history and history[-1].get("day") == today:
            history[-1] = entry
        else:
            history.append(entry)
        history = history[-90:]

        confidence = min(0.95, 0.30 + 0.10 * math.log10(1 + total))
        return {
            "qq": stat.sender_id,
            "name": stat.sender_name,
            "sentiment": {
                "label": label,
                "score": score,
                "confidence": round(confidence, 3),
                "trend": taxonomy.sentiment_trend(history, score),
                "samples": len(history),
                "first_day": first_day,
                "last_day": today,
                "type": type_key,
                "type_label": taxonomy.sentiment_type_label(type_key),
            },
            "dims": analyzer.dims_from_emotions(emotions),
            "emotions": emotions,
            "summary": summary,
            "keywords": keywords[:5],
            "engine": data.get("engine", "unknown"),
            "message_count": total,
            "message_count_total": total,
            "last_message_ts": stat.last_ts,
            "analyzed_at": time.time(),
            "analyzed_day": today,
            "positive_ratio": round(taxonomy.positive_ratio(emotions), 3),
            "daily": {
                "day": today,
                "score": round(day_score, 4),
                "events": events,
            },
            "history": history,
        }

    async def summarize_daily(self) -> int:
        if self._busy:
            return 0
        db = self._db_path()
        if not db:
            logger.warning("[affect_core] 找不到 conversations.db")
            return 0
        if self.release_mode == "stop":
            await self._ensure_ollama()
        self._busy = True
        done = 0
        try:
            for stat in db_source.list_senders(db):
                if not self.enabled:
                    break
                if stat.count < self.min_messages:
                    continue
                old = self.store.load(stat.sender_id)
                since = float(old.get("last_message_ts") or 0.0) if old else 0.0
                watermark = self._mark_watermark(stat.sender_id)
                if watermark > 0:
                    # 只推理「标记之后」的新消息
                    new_msgs = db_source.fetch_messages_after_id(db, stat.sender_id, watermark)
                else:
                    # 第一次：按时间增量取，推完立刻打上 id 水位
                    new_msgs = db_source.fetch_messages_since(db, stat.sender_id, since)
                contents = [m.content for m in new_msgs if (m.content or "").strip()]
                if len(contents) < self.min_daily_messages:
                    continue
                prior = self._prior_text(old)
                data = await self._infer(stat.sender_name, contents, prior)
                self.store.save(stat.sender_id, self._merge(old, stat, data, len(contents)))
                max_id = max((int(getattr(m, "id", 0) or 0) for m in new_msgs), default=0)
                self._mark_analyzed(stat.sender_id, max_id, len(contents))
                self._save_marks()
                logger.info(
                    f"[affect_core] {stat.sender_name} 推理 {len(contents)} 条（id≤{max_id} 已标记，下次不再推）"
                )
                done += 1
                await asyncio.sleep(1.0)
            self._rounds += 1
            self.state["daily_day"] = datetime.now().strftime("%Y-%m-%d")
            self.state["daily_ts"] = time.time()
            self._save_state()
            self._global_cache = (0.0, {})
            self._invalidate()
            self._write_snapshot(force=True)
        finally:
            self._busy = False
            try:
                await self._release_local_compute()
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[affect_core] 释放本地算力失败: {exc}")
        return done

    # ------------------------------------------------------------ 本地算力
    async def _release_local_compute(self) -> None:
        """情感推理结束后把本地算力收掉：先卸载模型，必要时再停 Ollama 进程。"""
        if not self.release_after_infer:
            return
        ok = await asyncio.to_thread(analyzer.unload_model, self.ollama_url, self.model)
        left = await asyncio.to_thread(analyzer.running_models, self.ollama_url)
        left_text = "、".join(left) if left else "无"
        if ok:
            logger.info(
                f"[affect_core] 本地算力已释放：卸载 {self.model}（仍驻留：{left_text}）"
            )
        else:
            logger.warning(f"[affect_core] 卸载 {self.model} 没有成功，Ollama 可能没在跑")
        if self.release_mode != "stop":
            return
        if left:
            logger.info(f"[affect_core] 还有模型驻留（{left_text}），先不动 Ollama 进程")
            return
        await self._stop_ollama()

    async def _stop_ollama(self) -> None:
        """结束 Ollama 进程（只在本机、且显存已经空了的时候做）。"""
        import subprocess

        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                ["taskkill", "/IM", "ollama.exe", "/F"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            out = ((proc.stdout or "") + (proc.stderr or "")).strip()
            if proc.returncode == 0:
                logger.info(f"[affect_core] 已结束 Ollama 进程：{out[:120]}")
            else:
                logger.info(f"[affect_core] 没有可结束的 Ollama 进程：{out[:120]}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[affect_core] 结束 Ollama 失败: {exc}")

    async def _ensure_ollama(self) -> bool:
        """release_mode=stop 时，推理前把 Ollama 拉起来（没配 exe 就跳过）。"""
        if await asyncio.to_thread(analyzer.running_models, self.ollama_url):
            return True
        if not self.ollama_exe:
            logger.warning(
                "[affect_core] Ollama 不在跑，且没有配置 ollama_exe，无法自动拉起"
            )
            return False
        import subprocess

        env = dict(os.environ)
        if self.ollama_model_dir:
            env["OLLAMA_MODELS"] = self.ollama_model_dir
        try:
            await asyncio.to_thread(
                subprocess.Popen,
                [self.ollama_exe, "serve"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[affect_core] 拉起 Ollama 失败: {exc}")
            return False
        for _ in range(20):
            await asyncio.sleep(1.0)
            if await asyncio.to_thread(analyzer.running_models, self.ollama_url):
                return True
            if await asyncio.to_thread(analyzer.list_models, self.ollama_url, 2.0):
                return True
        logger.warning("[affect_core] 拉起 Ollama 超时")
        return False

    # ------------------------------------------------------------ 消息与门控

    @staticmethod
    def _hhmm_minutes(value: str) -> int | None:
        try:
            hh, mm = str(value).strip().split(":")
            return int(hh) * 60 + int(mm)
        except Exception:  # noqa: BLE001
            return None

    def _in_quiet_window(self, now: datetime) -> bool:
        start = self._hhmm_minutes(self.group_quiet_start)
        end = self._hhmm_minutes(self.group_quiet_end)
        if start is None or end is None or start == end:
            return False
        cur = now.hour * 60 + now.minute
        if start < end:
            return start <= cur < end
        return cur >= start or cur < end

    def _is_directed(self, event: AstrMessageEvent, text: str) -> tuple[bool, str]:
        """这句话是不是在找我说话（@、回我、接着我上一句、开口就用「你」…）。"""
        if bool(getattr(event, "is_at_or_wake_command", False)):
            return True, "被 @ 或叫了名字"

        session = str(getattr(event, "unified_msg_origin", "") or "")
        me = ""
        try:
            me = str(event.get_self_id() or "")
        except Exception:  # noqa: BLE001
            me = ""
        last = self._last_reply.get(session) or {}

        # 1) 回复的是我的消息
        try:
            chain = list(getattr(getattr(event, "message_obj", None), "message", []) or [])
        except Exception:  # noqa: BLE001
            chain = []
        for comp in chain:
            if comp.__class__.__name__ != "Reply":
                continue
            rid = str(getattr(comp, "sender_id", "") or "")
            if me and rid and rid == me:
                return True, "在回我的消息"
            if last and time.time() - float(last.get("ts") or 0) <= 300:
                return True, "在回我的消息"

        # 2) 同一个人接着我刚说的话往下说
        if last:
            try:
                same = str(event.get_sender_id() or "") == str(last.get("qq") or "")
            except Exception:  # noqa: BLE001
                same = False
            if same and time.time() - float(last.get("ts") or 0) <= 180:
                return True, "接着刚才那句"

        t = (text or "").strip()
        if not t:
            return False, ""
        if "鲸屿" in t or "屿屿" in t or "大肥鱼" in t:
            return True, "话里提到我"
        if t[0] in "你您":
            return True, "开口就在对我说话"
        for pat in (
            "在吗",
            "在不在",
            "在么",
            "你说呢",
            "你觉得",
            "你怎么",
            "你为啥",
            "你干嘛",
            "你刚才",
            "你帮我",
            "你给我",
            "你去找",
            "你想不想",
        ):
            if pat in t:
                return True, f"问的是我（{pat}）"
        if ("你" in t or "您" in t) and (t.endswith("？") or t.endswith("?")):
            return True, "带问号、又提到你"
        return False, ""

    def _is_tired(self) -> bool:
        """此刻是否累了：八维疲劳为正，或情绪落在疲惫类。"""
        try:
            dims = ((self._view() or {}).get("mood") or {}).get("dims") or {}
            if float(dims.get("fatigue", 0.0) or 0.0) > self.group_tired_fatigue:
                return True
        except Exception:
            pass
        try:
            emo = str((self.state.get("last_card") or {}).get("emotion") or "")
        except Exception:
            emo = ""
        return any(k in emo for k in ("疲惫", "困", "累", "倦", "睡"))

    def _group_speak_allowed(self, text: str, energy: float) -> tuple[bool, str]:
        """没被点名的群消息：值不值得主动接这一句。"""
        now = datetime.now()
        if self._in_quiet_window(now):
            return False, f"静默时段 {self.group_quiet_start}-{self.group_quiet_end}"
        if self.group_mention_boost and (
            "鲸屿" in text or "屿屿" in text or "大肥鱼" in text
        ):
            self._group_hits.append(time.time())
            return True, "话里提到我"
        # 分档概率：能量只决定「多愿意开口」，不再叠加第二层惩罚，也不设条数上限
        if energy < 20:
            rate = self.group_rate_low
        elif energy < 40:
            rate = self.group_rate_mid
        elif energy < 70:
            rate = self.group_rate_high_mid
        else:
            rate = self.group_rate_high
        if self.group_tired_factor < 1.0 and self._is_tired():
            rate *= self.group_tired_factor
        if rate <= 0.0:
            return False, f"能量 {energy:.0f}%，不接"
        if random.random() < rate:
            self._group_hits.append(time.time())
            return True, f"按 {rate:.0%} 的概率接一句"
        return False, f"先不接（{rate:.0%} 没中）"

    @filter.event_message_type(
        filter.EventMessageType.ALL,
        priority=sys.maxsize - 20,
    )
    async def on_message(self, event: AstrMessageEvent) -> None:
        if not self.enabled:
            return
        try:
            qq = str(event.get_sender_id() or "")
            session = str(getattr(event, "unified_msg_origin", "") or "")
            if qq and session:
                private = False
                try:
                    private = bool(event.is_private_chat())
                except Exception:  # noqa: BLE001
                    private = "FriendMessage" in session
                old = self._sessions.get(qq)
                if not old or old.get("session") != session or old.get("name") != str(
                    event.get_sender_name() or qq
                ):
                    self._sessions[qq] = {
                        "session": session,
                        "name": str(event.get_sender_name() or qq),
                        "private": private,
                        "ts": time.time(),
                    }
                    self._save_sessions()
                self.state["active_qq"] = qq
                self.state["active_ts"] = time.time()
                self._invalidate()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[affect_core] 记录会话失败: {exc}")

        try:
            text = str(getattr(event, "message_str", "") or "")
        except Exception:  # noqa: BLE001
            text = ""
        self._appraise(event, text)

        # 群聊场合分级：与「门控」（低电切便宜模型）解耦，关掉门控也依然生效
        try:
            energy0 = self._energy_now()[2]
            directed0, why0 = self._is_directed(event, text)
            if (not event.is_private_chat()) and not directed0:
                allow, why = self._group_speak_allowed(text, energy0)
                if not allow:
                    event.stop_event()
                    logger.info(f"[affect_core] 这句不接：{why}")
                    return
                logger.debug(f"[affect_core] 接一句：{why}")
            elif why0:
                logger.debug(f"[affect_core] 这句接：{why0}")
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[affect_core] 群聊分级失败: {exc}")

        if not self.gate_enabled:
            return
        try:
            energy = self._energy_now()[2]
            addressed = bool(getattr(event, "is_at_or_wake_command", False))
            is_group = not event.is_private_chat()
            if not self._provider_available():
                return
            if energy < self.thinking_min or (is_group and not addressed):
                event.set_extra(PROVIDER_EXTRA_KEY, self.fast_provider)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[affect_core] 门控失败: {exc}")

    def _provider_available(self) -> bool:
        if self._provider_ok is None:
            try:
                provider = self.context.get_provider_by_id(self.fast_provider)
            except Exception:  # noqa: BLE001
                provider = None
            self._provider_ok = provider is not None
            if not self._provider_ok:
                logger.warning(
                    f"[affect_core] 找不到快速提供商 {self.fast_provider!r}，门控不生效"
                )
        return self._provider_ok

    # ------------------------------------------------------------ 提示注入

    def _insult_verdict(self, event: AstrMessageEvent, text: str) -> dict:
        """辱骂判定：词表 + 语境加权，而不是命中即成立。"""
        if not text:
            return {"insult": False, "severity": 0.0, "term": "", "reasons": []}
        directed = self._targets_self_or_owner(event)
        if not self.insult_context:
            hit = any(word in text for word in self.negative_keywords)
            return {
                "insult": hit,
                "severity": 1.0 if hit else 0.0,
                "term": "",
                "reasons": ["纯关键词"],
            }
        verdict = insult.detect(
            text, directed=directed, extra_terms=self.negative_keywords
        )
        if self.negative_requires_target and not directed:
            verdict["insult"] = False
        return verdict

    def _insulted(self, event: AstrMessageEvent, text: str) -> bool:
        return bool(self._insult_verdict(event, text)["insult"])

    def _mark_burst(self, kind: str, strength: float = 1.0) -> None:
        """明确的事件（被骂/被夸/求陪成真）直接算突变，不走慢平滑。"""
        if not self.burst_enabled:
            return
        self.state["emotion_burst"] = {
            "kind": kind,
            "ts": time.time(),
            "strength": max(0.0, min(1.0, float(strength))),
        }

    def _negative_trigger(self, text: str) -> None:
        levels = self.state.setdefault("h", {})
        bumps = {
            "cortisol": 0.10,
            "adrenaline": 0.06,
            "norepinephrine": 0.04,
            "serotonin": -0.08,
            "dopamine": -0.05,
            "endorphin": -0.03,
            "oxytocin": -0.02,
        }
        for name, delta in bumps.items():
            levels[name] = max(0.0, min(1.0, float(levels.get(name, 0.5)) + delta))
        self.state["negative_until"] = time.time() + random.uniform(15, 35) * 60
        self.state["ts"] = 0.0
        self._mark_burst("insult", 1.0)

    def _targets_self_or_owner(self, event: AstrMessageEvent) -> bool:
        try:
            if event.is_private_chat():
                return True
            if bool(getattr(event, "is_at_or_wake_command", False)):
                return True
            self_id = str(event.get_self_id() or "")
            return str(event.get_sender_id() or "") == self_id
        except Exception:  # noqa: BLE001
            return False

    def _appraise(self, event: AstrMessageEvent, text: str) -> None:
        """事件级评价：意图 × 应对能力 × 习惯化 × 依恋风格。

        一次乘法组合就决定「愤怒」还是「受伤」，以及持续多久。
        """
        if not self.appraisal_enabled or not text:
            return
        verdict = self._insult_verdict(event, text)
        insulted_now = bool(verdict.get("insult"))
        praise = any(word in text for word in PRAISE_KEYWORDS)
        if not insulted_now and not praise:
            return

        qq = str(self.state.get("active_qq") or "")
        kind = "insult" if insulted_now else "praise"
        self._mark_burst(kind, 0.9)
        hab = self.state.setdefault("habituation", {})
        key = f"{qq}:{kind}"
        count = int(hab.get(key, 0))
        hab[key] = count + 1
        # 习惯化：第 n 次同类事件的冲击，25% 封底
        decay = max(0.25, 1.0 - self.habituation_decay * count)

        view = self._view()
        style = (view.get("social") or {}).get("attachment", "secure")
        style_k = {"anxious": 1.25, "secure": 1.0, "avoidant": 0.6}.get(style, 1.0)
        dominance = float(view["dims"].get("dominance", 0.0))
        coping = clamp(
            self._energy_now()[2] / 100 * 0.7 + (dominance + 1) / 2 * 0.3, 0.0, 1.0
        )

        severity = (
            float(verdict.get("severity", 0.0)) if insulted_now else 0.55
        ) * decay * style_k
        levels = self.state.setdefault("h", {})

        def bump(name: str, delta: float) -> None:
            levels[name] = clamp(float(levels.get(name, 0.5)) + delta, 0.0, 1.0)

        if insulted_now:
            # 有意 → 愤怒路线；无意 → 受伤路线
            intentional = 1.0 if self._targets_self_or_owner(event) else 0.45
            anger = severity * intentional * (0.6 + 0.4 * coping)
            hurt = severity * (1.0 - intentional) + severity * 0.3
            bump("adrenaline", 0.10 * anger)
            bump("cortisol", 0.08 * (anger + hurt))
            bump("serotonin", -0.06 * hurt)
            bump("oxytocin", -0.05 * severity)
            # 能应对 → 情绪来得快去得快；不能应对 → 停留更久
            window = (20.0 if coping > 0.5 else 45.0) * (
                0.7 if style == "avoidant" else 1.0
            )
            self.state["negative_until"] = time.time() + window * 60
            self.state["last_appraisal"] = {
                "kind": "anger" if anger > hurt else "hurt",
                "severity": round(severity, 3),
                "coping": round(coping, 3),
            }
        else:
            bump("oxytocin", 0.06 * severity)
            bump("dopamine", 0.05 * severity)
            bump("serotonin", 0.04 * severity)
            self.state["last_appraisal"] = {
                "kind": "praise",
                "severity": round(severity, 3),
            }
        self._invalidate()

    @filter.on_llm_request(priority=sys.maxsize - 3)
    async def inject(self, event: AstrMessageEvent, req) -> None:
        if not self.enabled or not self.inject_prompt:
            return
        try:
            text = event.message_str or ""
        except Exception:  # noqa: BLE001
            text = ""

        insulted = self._insulted(event, text)
        if insulted and self.negative_trigger and not self.appraisal_enabled:
            self._negative_trigger(text)
        if insulted:
            self._invalidate()

        self._drain_desktop_events()
        self.mood.update(self._energy_now()[2], self._neuro_bias())
        self._invalidate()
        view = self._view()
        dims = view["dims"]
        emotion = view["emotion"]
        emo_detail = self.mood.emotion_detail(dims)
        emotion_text = self.mood.emotion_text(dims)
        traits = view["traits"]
        social = view["social"]
        _, _, energy = self._energy_now()
        style = "；".join(self.mood.style_lines(dims, traits)[:4])

        # 只输出明显偏离中性的性格项，避免每轮搬 18 个数字
        trait_items = [
            (key, traits[key])
            for key in TRAIT_LABELS
            if abs(traits[key] - 0.5) >= 0.15
        ][:8]
        if not trait_items:
            trait_items = [("lively", traits["lively"])]

        # 卡片刻意压短：只保留影响生成的关键信息，减少每轮消耗
        parts = [
            "",
            "【状态｜优先于人格卡同名特质】",
            f"能量{energy:.0f}%({self.energy.tier(energy)})｜心情{emotion_text}｜基调{emo_detail.get('mood') or ''}",
            "八维 " + " ".join(f"{DIM_SHORT[k]}{dims[k]:+.2f}" for k in DIM_LABELS),
            "性格 " + " ".join(
                f"{TRAIT_LABELS[k]}{value:.2f}" for k, value in trait_items
            ),
            f"说法 {style}",
        ]
        if social:
            top_txt = "、".join(f"{n}{float(v):.1f}" for n, v in social.get("top") or [])
            attachment = social.get("attachment", "secure")
            att_txt = (
                f"[{ATTACHMENT_LABELS[attachment]}]" if attachment != "secure" else ""
            )
            parts.append(
                f"对方 {social.get('name', '')} "
                f"{social.get('label', '')}·{social.get('type_label', '')}"
                f"({social.get('score', 0.0):+.2f}){att_txt}"
                + (f" {top_txt}" if top_txt else "")
            )
            anchors = [str(k) for k in (social.get("keywords") or [])[:4] if str(k).strip()]
            if anchors:
                parts.append("记忆 " + "、".join(anchors))
        hint = EMOTIONS.get(emotion, ("",))[5] if emotion in EMOTIONS else ""
        if hint:
            parts.append(f"感觉 {hint}")
        level = str(emo_detail.get("level") or "")
        if level == "强":
            parts.append("这会儿情绪挺明显，别压着，也别放大。")
        elif level == "轻":
            parts.append("这会儿情绪很淡，别演得很满。")
        if insulted and self.retaliate_enabled:
            parts.append("被骂了：可以一句短促带刺地怼回去，别攻击家人，一两句就够。")
        comfort_until = float(self.state.get("comfort_open_until", 0.0) or 0.0)
        if comfort_until > time.time():
            mins = int((comfort_until - time.time()) / 60)
            parts.append(
                f"刚才（{mins} 分钟内）是你自己开口说「能陪我说说话吗」，对方应了。"
                "这一段别用「累」「你去忙吧」把话关掉：先接住对方，至少聊两三轮再提睡觉；"
                "累可以说，但别拿它结束对话。"
            )

        card = "\n".join(parts) + "\n"
        try:
            req.system_prompt = (req.system_prompt or "") + card
        except Exception:  # noqa: BLE001
            pass

        self.state["last_card"] = {
            "ts": time.time(),
            "emotion": emotion,
            "energy": round(energy, 1),
            "text": card.strip(),
        }
        self.state["card_count"] = int(self.state.get("card_count", 0)) + 1
        self._save_state()
        self._write_snapshot()

    # ------------------------------------------------------------ 求安慰

    async def _seek_comfort(self, force: bool = False) -> str:
        if not self.enabled or not self.comfort_enabled:
            return "求安慰未启用"
        dims = self._view()["dims"]
        emotion = self._view()["emotion"]
        if not force and emotion not in self.comfort_emotions:
            return f"当前是「{emotion}」，不需要求安慰"
        now = time.time()
        if not force:
            energy = self._energy_now()[2]
            if energy < self.comfort_min_energy:
                return (
                    f"能量只有 {energy:.0f}%，太累了，先不找人说话"
                    "（这时候开了口也只会把人推走）"
                )
        if not force:
            last = float(self.state.get("last_comfort_ts", 0.0) or 0.0)
            if now - last < self.comfort_cooldown:
                return f"刚找过，还要等 {int((self.comfort_cooldown - (now - last)) / 60)} 分钟"

        target = self._pick_comfort_target()
        if not target:
            return "没找到可以找的人（没有可用会话）"
        qq, who, session = target
        text = self.comfort_message or self._comfort_text(emotion, who)
        text = text.replace("{emotion}", emotion).replace("{name}", who)
        try:
            sent = await self.context.send_message(
                session, MessageChain().message(text)
            )
        except Exception as exc:  # noqa: BLE001
            return f"发送失败：{exc}"
        if not sent:
            return f"没发出去（{who} 的会话可能已失效）"
        self.state["last_comfort_ts"] = now
        self.state["last_comfort_to"] = qq
        # 开一个「求陪窗口」：这段时间里别用累把对方推开
        self.state["comfort_open_until"] = now + self.comfort_window
        self.state["comfort_open_to"] = qq
        self._save_state()
        return f"已向 {who}（{qq}）发出求安慰消息"

    def _comfort_text(self, emotion: str, who: str) -> str:
        """按情绪挑一句自己的说法，避开上次用过的那句。"""
        pool = COMFORT_LINES.get(emotion) or COMFORT_LINES["_default"]
        last = str(self.state.get("last_comfort_text") or "")
        choices = [t for t in pool if t != last] or list(pool)
        text = random.choice(choices)
        hour = datetime.now().hour
        if (hour >= 23 or hour < 6) and "睡" not in text:
            text = f"{text}（这会儿还没睡）"
        text = text.replace("{name}", who)
        self.state["last_comfort_text"] = text
        return text

    def _pick_comfort_target(self) -> tuple[str, str, str] | None:
        def session_of(qq: str) -> tuple[str, str] | None:
            info = self._sessions.get(qq)
            if not isinstance(info, dict):
                return None
            session = str(info.get("session") or "")
            if not session:
                return None
            if not info.get("private") and not self.comfort_allow_group:
                return None
            return session, str(info.get("name") or qq)

        if self.comfort_target_qq:
            hit = session_of(self.comfort_target_qq)
            return (self.comfort_target_qq, hit[1], hit[0]) if hit else None

        best = None
        for profile in self.store.list_all():
            qq = str(profile.get("qq") or "")
            if not qq:
                continue
            sent = profile.get("sentiment") or {}
            dims = profile.get("dims") or {}
            weight = float(sent.get("score", 0.0)) + 0.4 * float(
                dims.get("affiliation", 0.0)
            )
            if weight <= 0:
                continue
            hit = session_of(qq)
            if not hit:
                continue
            if best is None or weight > best[0]:
                best = (weight, qq, hit[1], hit[0])
        return (best[1], best[2], best[3]) if best else None

    # ------------------------------------------------------------ 命令

    def _status_lines(self) -> list[str]:
        base, bias, energy = self._energy_now()
        view = self._view()
        dims = view["dims"]
        emotion = view["emotion"]
        traits = view["traits"]
        g = self._global_state()
        lines = [
            f"心情：{emotion}｜能量：{energy:.0f}%（{self.energy.tier(energy)}）",
            f"  基础 {base:.0f}%｜修正 {bias:+.1f}%",
            "八维：" + _fmt_dims(dims),
            "性格：" + "／".join(f"{TRAIT_LABELS[k]} {traits[k]:.2f}" for k in list(TRAIT_LABELS)[:6]),
            "说话方式：" + "；".join(self.mood.style_lines(dims, traits)),
        ]
        social = view["social"]
        if social:
            lines.append(
                f"当前对象：{social.get('name', '')}｜"
                f"情感 {social.get('label', '')}·{social.get('type_label', '')}"
                f"（{social.get('score', 0.0):+.2f}）"
            )
        lines.append(
            f"共享内分泌："
            + ("、".join(f"{HORMONE_LABELS.get(k, k)} {v:+.3f}" for k, v in g["neuro"].items()) or "无")
            + f"｜稳态负荷 {g['energy']:+.1f}%"
        )
        return lines

    @filter.command("状态", alias={"affect_status"})
    async def status_cmd(self, event: AstrMessageEvent):
        if not self.enabled:
            yield event.plain_result("影响核心未启用。")
            return
        yield event.plain_result("\n".join(self._status_lines()))

    @filter.command("心情", alias={"mood"})
    async def mood_cmd(self, event: AstrMessageEvent):
        if not self.enabled or not self.commands_enabled:
            return
        view = self._view()
        dims = view["dims"]
        yield event.plain_result(
            f"现在的心情：{view['emotion']}"
            f"（愉悦 {dims['valence']:+.2f}｜唤醒 {dims['arousal']:+.2f}）"
        )

    @filter.command("激素", alias={"hormones"})
    async def hormones_cmd(self, event: AstrMessageEvent):
        if not self.enabled or not self.commands_enabled:
            return
        levels = self.state.get("h") or {}
        lines = []
        for name, spec in HORMONES.items():
            value = float(levels.get(name, spec["mean"]))
            bar = "█" * int(round(value * 10)) + "░" * (10 - int(round(value * 10)))
            lines.append(f"{spec['label']:<6}{bar} {value:.2f}  {spec['desc']}")
        yield event.plain_result("\n".join(lines))

    @filter.command("能量", alias={"energy"})
    async def energy_cmd(self, event: AstrMessageEvent):
        if not self.enabled or not self.commands_enabled:
            return
        base, bias, energy = self._energy_now()
        yield event.plain_result(
            f"当前能量：{energy:.1f}%（{self.energy.tier(energy)}）\n"
            f"  昼夜基础 {base:.1f}%｜激素/情绪/负荷 {bias:+.1f}%\n"
            f"接话率：{self.energy.rate(energy):.0%}｜深度思考阈值 {self.thinking_min}%"
        )

    def _render_profile(self, profile: dict) -> str:
        sent = profile.get("sentiment") or {}
        lines = [
            f"情感画像 · {profile.get('name', '')}（{profile.get('qq', '')}）",
            f"机器人对 TA：{sent.get('label', '中')}·{sent.get('type_label', '')}"
            f"（{float(sent.get('score', 0)):+.2f}）"
            f"｜趋势 {sent.get('trend', '稳定')}｜已观察 {sent.get('samples', 0)} 天",
            "长期八维：" + _fmt_dims(profile.get("dims") or {}),
            "长期感受：" + _fmt_top(profile.get("emotions") or {}, 5),
        ]
        if profile.get("summary"):
            lines.append("概括：" + str(profile["summary"]))
        return "\n".join(lines)

    def _resolve_target(self, event: AstrMessageEvent, text: str = "") -> tuple[str, str]:
        try:
            self_id = str(event.get_self_id() or "")
            for msg in event.get_messages():
                qq = str(getattr(msg, "qq", "") or "")
                if qq and qq != self_id:
                    profile = self.store.load(qq)
                    return qq, (profile or {}).get("name", qq)
        except Exception:  # noqa: BLE001
            pass
        digits = "".join(ch for ch in (text or "") if ch.isdigit())
        if len(digits) >= 5:
            profile = self.store.load(digits)
            return digits, (profile or {}).get("name", digits)
        me = str(self.state.get("active_qq") or "")
        profile = self.store.load(me) if me else None
        return me, (profile or {}).get("name", me or "未知")

    @filter.command("情感", alias={"emotion"})
    async def sentiment_cmd(self, event: AstrMessageEvent):
        if not self.enabled or not self.commands_enabled:
            return
        qq, name = self._resolve_target(event, event.message_str or "")
        profile = self.store.load(qq) if qq else None
        if not profile:
            yield event.plain_result(f"还没有「{name}」的情感画像。")
            return
        yield event.plain_result(self._render_profile(profile))

    @filter.command("情感列表", alias={"emotion_list"})
    async def sentiment_list_cmd(self, event: AstrMessageEvent):
        if not self.enabled or not self.commands_enabled:
            return
        people = self.store.list_all()
        if not people:
            yield event.plain_result("还没有任何情感画像。")
            return
        lines = [f"已分析 {len(people)} 人："]
        for p in people:
            sent = p.get("sentiment") or {}
            lines.append(
                f"· {p.get('name', '')}（{p.get('qq', '')}）"
                f" {sent.get('label', '中')}·{sent.get('type_label', '')}"
                f" {float(sent.get('score', 0)):+.2f}"
            )
        yield event.plain_result("\n".join(lines))

    @permission_type(PermissionType.ADMIN)
    @filter.command("安慰", alias={"seek_comfort"})
    async def comfort_cmd(self, event: AstrMessageEvent):
        if not self.enabled:
            yield event.plain_result("影响核心未启用。")
            return
        yield event.plain_result(await self._seek_comfort(force=True))

    @permission_type(PermissionType.ADMIN)
    @filter.command("情感刷新", alias={"emotion_refresh"})
    async def refresh_cmd(self, event: AstrMessageEvent):
        if not self.enabled:
            yield event.plain_result("影响核心未启用。")
            return
        yield event.plain_result("开始重新总结…")
        done = await self.summarize_daily()
        yield event.plain_result(f"完成，更新了 {done} 人。")

    # ------------------------------------------------------------ 人味三件套

    def _clean_text(self, text: str) -> str:
        out = text or ""
        if self.strip_markdown:
            for pattern, repl in MARKDOWN_RULES:
                out = pattern.sub(repl, out)
        for phrase in AI_PHRASES:
            out = out.replace(phrase, "")
        out = re.sub(r"\n{3,}", "\n\n", out).strip()
        out = re.sub(r"\n\s*\n", "\n", out).strip()
        if len(out) > self.max_chars:
            cut = out[: self.max_chars]
            for sep in ("。", "！", "？", "\n", "，"):
                idx = cut.rfind(sep)
                if idx >= self.max_chars * 0.5:
                    cut = cut[: idx + 1]
                    break
            out = cut
        return out

    @filter.on_llm_request(priority=sys.maxsize - 6)
    async def inject_style_learn(self, event: AstrMessageEvent, req) -> None:
        """风格约束 + 记忆召回，独立于情绪卡片。"""
        if not self.enabled:
            return
        blocks: list[str] = []
        if self.style_enabled:
            directive = self.style.directive()
            if directive:
                blocks.append(directive)
        if self.learn_enabled:
            try:
                text = event.message_str or ""
            except Exception:  # noqa: BLE001
                text = ""
            if text:
                try:
                    qq = str(event.get_sender_id() or "")
                    name = str(event.get_sender_name() or "")
                except Exception:  # noqa: BLE001
                    qq, name = "", ""
                added = self.knowledge.learn_from(text, qq, name)
                if added and self.debug:
                    logger.info(f"[affect_core] 学到 {len(added)} 条：{added[:3]}")
                recalled = self.knowledge.recall(text, self.learn_recall_limit)
                if recalled:
                    facts = "\n".join(f"· {item['fact']}" for item in recalled)
                    blocks.append(f"【你记得的事】\n{facts}")
        if blocks:
            try:
                req.system_prompt = (req.system_prompt or "") + "\n\n" + "\n".join(blocks)
            except Exception:  # noqa: BLE001
                pass

    @filter.on_llm_response(priority=sys.maxsize - 20)
    async def remember_reply(self, event: AstrMessageEvent, response) -> None:
        """记住「我刚回过谁」，下一句同一个人接着说话时直接接。"""
        try:
            session = str(getattr(event, "unified_msg_origin", "") or "")
            if not session:
                return
            self._last_reply[session] = {
                "ts": time.time(),
                "qq": str(event.get_sender_id() or ""),
            }
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[affect_core] 记录回话失败: {exc}")

    @filter.on_llm_response(priority=sys.maxsize - 6)
    async def watch_response(self, event: AstrMessageEvent, response) -> None:
        if not self.enabled or not self.revise_enabled:
            return
        try:
            text = getattr(response, "completion_text", "") or ""
        except Exception:  # noqa: BLE001
            return
        if len(text) < 10 or not any(word in text for word in UNCERTAIN):
            return
        if random.random() > self.revise_rate:
            return
        now = time.time()
        if now - float(self.state.get("last_revise_ts", 0.0)) < self.revise_cooldown:
            return
        self.state["last_revise_ts"] = now
        try:
            event.set_extra("_affect_revise", True)
        except Exception:  # noqa: BLE001
            pass
        if self.debug:
            logger.info(
                f"[affect_core] 触发自我修正｜回复 {len(text)} 字｜命中不确定词"
            )

    @filter.after_message_sent(priority=sys.maxsize - 6)
    async def after_sent_hook(self, event: AstrMessageEvent) -> None:
        if not self.enabled:
            return
        try:
            already = bool(event.get_extra("_affect_style_recorded", False))
        except Exception:  # noqa: BLE001
            already = False
        if self.style_enabled and not already:
            try:
                texts = event.get_extra(
                    "_send_message_to_user_current_session_plain_texts", []
                ) or []
                recorded = [t for t in texts if isinstance(t, str) and t.strip()]
                for item in recorded:
                    self.style.record(item)
                if recorded:
                    self.style.save()
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[affect_core] 记录风格失败: {exc}")

        try:
            pending = bool(event.get_extra("_affect_revise", False))
        except Exception:  # noqa: BLE001
            pending = False
        if not pending:
            return
        try:
            event.set_extra("_affect_revise", False)
        except Exception:  # noqa: BLE001
            pass
        task = asyncio.create_task(self._send_correction(event))
        self._revise_tasks.add(task)
        task.add_done_callback(self._revise_tasks.discard)

    async def _send_correction(self, event: AstrMessageEvent) -> None:
        await asyncio.sleep(random.uniform(2.5, 6.5))
        text = random.choice(CORRECTIONS)
        try:
            await self.context.send_message(
                event.unified_msg_origin, MessageChain().message(text)
            )
            logger.info(f"[affect_core] 已发送自我修正：{text}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[affect_core] 自我修正发送失败: {exc}")

    @filter.on_decorating_result(priority=sys.maxsize - 6)
    async def tidy_result(self, event: AstrMessageEvent) -> None:
        if not self.enabled:
            return
        try:
            result = event.get_result()
        except Exception:  # noqa: BLE001
            return
        if not result or not getattr(result, "chain", None):
            return
        for comp in result.chain:
            if isinstance(comp, Plain):
                cleaned = self._clean_text(getattr(comp, "text", ""))
                if cleaned:
                    comp.text = cleaned
        if self.style_enabled:
            try:
                sent = [
                    getattr(c, "text", "")
                    for c in result.chain
                    if isinstance(c, Plain) and getattr(c, "text", "").strip()
                ]
                if sent:
                    for item in sent:
                        self.style.record(item)
                    self.style.save()
                    if self.debug:
                        logger.debug(f"[affect_core] 记录风格样本 {len(sent)} 条")
                    event.set_extra("_affect_style_recorded", True)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[affect_core] 记录风格失败: {exc}")

    @filter.command("记忆", alias={"what_i_know"})
    async def knowledge_cmd(self, event: AstrMessageEvent):
        stats = self.knowledge.stats()
        if not stats["total"]:
            yield event.plain_result("还什么都没记住。")
            return
        lines = [f"记住了 {stats['total']} 条："]
        for item in self.knowledge.recent(6):
            lines.append(f"· {item.get('fact', '')}")
        yield event.plain_result("\n".join(lines))

    @filter.command("风格", alias={"my_style"})
    async def style_cmd(self, event: AstrMessageEvent):
        stats = self.style.stats()
        if not stats["samples"]:
            yield event.plain_result("还没有样本，先聊几句。")
            return
        yield event.plain_result(
            f"样本 {stats['samples']} 条｜平均 {stats['avg_chars']} 字｜"
            f"短句 {stats['short_ratio']:.0%}｜表情 {stats['emoji_ratio']:.0%}｜"
            f"反问 {stats['question_ratio']:.0%}\n"
            f"常用语气词：{''.join(stats['top_particles']) or '无'}"
        )

    # ------------------------------------------------------------ 页面

    def _register_api(self) -> None:
        try:
            if not hasattr(self.context, "register_web_api"):
                return
            for prefix in ("/astrbot_plugin_affect_core", "/affect_core"):
                route = f"{prefix}/page/data"
                try:
                    self.context.register_web_api(
                        route, self._api_data, ["GET"], "Affect core data"
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"[affect_core] 注册 {route} 失败: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[affect_core] 注册页面 API 失败: {exc}")

    async def _api_data(self):
        return self._payload()

    def _payload(self) -> dict:
        base, bias, energy = self._energy_now()
        view = self._view()
        dims = view["dims"]
        emotion = view["emotion"]
        traits = view["traits"]
        return {
            "mood": {
                "emotion": emotion,
                "emotion_text": self.mood.emotion_text(dims),
                "dims": dims,
                "dim_labels": DIM_LABELS,
                "traits": traits,
                "trait_labels": TRAIT_LABELS,
                "style": self.mood.style_lines(dims, traits),
                "hormones": self.state.get("h") or {},
                "hormone_labels": HORMONE_LABELS,
            },
            "energy": {
                "base": round(base, 1),
                "bias": round(bias, 1),
                "effective": round(energy, 1),
                "tier": self.energy.tier(energy),
                "rate": round(self.energy.rate(energy), 2),
                "sleep_debt": round(float(self.state.get("sleep_debt", 0.0)), 1),
            },
            "social": view["social"],
            "comfort": {
                "open": float(self.state.get("comfort_open_until", 0.0) or 0.0)
                > time.time(),
                "until": float(self.state.get("comfort_open_until", 0.0) or 0.0),
                "to": str(self.state.get("comfort_open_to") or ""),
                "min_energy": self.comfort_min_energy,
            },
            "gate": {
                "enabled": bool(self.gate_enabled),
                "thinking_min": int(self.thinking_min),
                "fast_provider": self.fast_provider,
                "scope": "qq_only",
            },
            "desktop": {
                "events": int(self.state.get("desktop_events", 0) or 0),
                "offset": int(self.state.get("desktop_offset", 0) or 0),
                "last_event": self.state.get("desktop_last_event"),
                "queue": str(self._desktop_path()),
            },
            "endocrine": self._global_state(),
            "people": self.store.list_all(),
            "card": self.state.get("last_card") or {},
            "meta": {
                "model": self.model,
                "daily_run_at": self.daily_run_at,
                "daily_day": self.state.get("daily_day"),
                "page_refresh_minutes": self.page_refresh_minutes,
                "ts": time.time(),
            },
        }

    def _write_snapshot(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_snapshot < 30.0:
            return
        self._last_snapshot = now
        try:
            path = Path(__file__).parent / "pages" / "affect" / "data.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self._payload(), ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[affect_core] 写页面快照失败: {exc}")





