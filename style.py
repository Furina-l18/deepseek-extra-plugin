"""说话风格统计：从机器人自己发过的话里学，而不是靠人设文字演。

只统计可量化的东西：句长、语气词、标点习惯、表情比例。
样本不够时不给建议，避免用三条消息就总结出"风格"。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

PARTICLES = ("啊", "呀", "吧", "呢", "嘛", "哦", "啦", "诶", "嗯", "喔", "噢", "咯")
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)


class StyleProfile:
    """机器人的自画像式风格档案。"""

    def __init__(self, path: Path, min_samples: int = 5):
        self.path = path
        self.min_samples = min_samples
        self.data = self._load()

    def _load(self) -> dict:
        default = {
            "count": 0,
            "chars": 0,
            "short": 0,
            "long": 0,
            "emoji": 0,
            "question": 0,
            "bang": 0,
            "tilde": 0,
            "particles": {},
            "recent": [],
        }
        try:
            if self.path.is_file():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    default.update(raw)
        except Exception:  # noqa: BLE001
            pass
        return default

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass

    def record(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        d = self.data
        n = len(text)
        d["count"] = int(d.get("count", 0)) + 1
        d["chars"] = int(d.get("chars", 0)) + n
        if n <= 20:
            d["short"] = int(d.get("short", 0)) + 1
        if n >= 80:
            d["long"] = int(d.get("long", 0)) + 1
        if EMOJI_RE.search(text):
            d["emoji"] = int(d.get("emoji", 0)) + 1
        if "?" in text or "？" in text:
            d["question"] = int(d.get("question", 0)) + 1
        if "!" in text or "！" in text:
            d["bang"] = int(d.get("bang", 0)) + 1
        if "~" in text or "～" in text:
            d["tilde"] = int(d.get("tilde", 0)) + 1
        particles = d.get("particles") or {}
        for p in PARTICLES:
            c = text.count(p)
            if c:
                particles[p] = int(particles.get(p, 0)) + c
        d["particles"] = particles
        recent = [r for r in (d.get("recent") or []) if isinstance(r, str)]
        recent.append(text[:40])
        d["recent"] = recent[-8:]

    # ------------------------------------------------------------------

    def _ratio(self, key: str) -> float:
        n = int(self.data.get("count", 0)) or 1
        return int(self.data.get(key, 0)) / n

    def top_particles(self, k: int = 3) -> list[tuple[str, int]]:
        items = (self.data.get("particles") or {}).items()
        return sorted(items, key=lambda kv: kv[1], reverse=True)[:k]

    def directive(self) -> str:
        """生成一段紧凑的约束，样本不足时返回空串。"""
        n = int(self.data.get("count", 0))
        if n < self.min_samples:
            return ""
        avg = int(self.data.get("chars", 0)) / n
        short = self._ratio("short")
        emoji = self._ratio("emoji")
        question = self._ratio("question")
        tilde = self._ratio("tilde")
        parts = [f"你平时一条回复平均 {avg:.0f} 字"]
        if short >= 0.6:
            parts.append("多数不超过 20 字")
        elif short <= 0.25:
            parts.append("偶尔也会写长一点")
        if emoji >= 0.35:
            parts.append("常带表情")
        elif emoji <= 0.05:
            parts.append("几乎不用表情")
        if question >= 0.3:
            parts.append("爱用反问")
        if tilde >= 0.25:
            parts.append("句尾常带「~」")
        tops = self.top_particles(3)
        if tops:
            parts.append("常用语气词：" + "".join(p for p, _ in tops))
        return "你的说话习惯：" + "，".join(parts) + "。保持这个节奏，不要突然变成客服腔。"

    def stats(self) -> dict:
        n = int(self.data.get("count", 0)) or 1
        return {
            "samples": int(self.data.get("count", 0)),
            "avg_chars": round(int(self.data.get("chars", 0)) / n, 1),
            "short_ratio": round(self._ratio("short"), 3),
            "emoji_ratio": round(self._ratio("emoji"), 3),
            "question_ratio": round(self._ratio("question"), 3),
            "top_particles": [p for p, _ in self.top_particles(5)],
            "updated": time.time(),
        }
