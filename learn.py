"""自我学习：把"别人教给它的东西"记下来，之后能想起来。

不追求"什么都学"，只认明确的信号：
- 让我记住 / 记一下
- 我叫 X / 我的生日是 X / 我喜欢 X
- X 叫 Y（术语、外号）
其余一律不记，避免把闲聊当知识。

召回用字符二元组重叠度，不依赖分词库。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

PATTERNS: list[tuple[str, str]] = [
    (r"(?:记住|记一下|记着|别忘了)[：:,，]?\s*(.{2,80})", "tell"),
    (r"我叫\s*([^\s，。！？、]{1,12})", "name"),
    (r"我的生日是\s*([^\s，。！？]{2,20})", "birthday"),
    (r"我喜欢\s*([^\s，。！？、]{1,30})", "like"),
    (r"我不喜欢\s*([^\s，。！？、]{1,30})", "dislike"),
    (r"([^\s，。！？、]{1,12})\s*叫\s*([^\s，。！？、]{1,20})", "alias"),
]

NOISE = ("什么", "怎么", "为什么", "是不是", "可不可以", "能不能")


def _bigrams(text: str) -> set[str]:
    text = re.sub(r"\s+", "", text or "")
    if len(text) < 2:
        return {text} if text else set()
    return {text[i : i + 2] for i in range(len(text) - 1)}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())[:120]


class KnowledgeStore:
    def __init__(self, path: Path, max_facts: int = 800):
        self.path = path
        self.max_facts = max_facts
        self.facts: list[dict] = []
        self._load()

    def _load(self) -> None:
        try:
            if self.path.is_file():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    self.facts = [f for f in raw if isinstance(f, dict)]
        except Exception:  # noqa: BLE001
            self.facts = []

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if len(self.facts) > self.max_facts:
                self.facts = sorted(
                    self.facts, key=lambda f: f.get("hits", 0), reverse=True
                )[: self.max_facts]
            self.path.write_text(
                json.dumps(self.facts, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------

    def learn_from(self, text: str, qq: str = "", name: str = "") -> list[str]:
        """从一句话里抽取可记的事实，返回新增的条目。"""
        text = (text or "").strip()
        if not text or len(text) > 300:
            return []
        added: list[str] = []
        for pattern, kind in PATTERNS:
            for match in re.finditer(pattern, text):
                fact = _norm(match.group(match.lastindex or 0))
                if not fact or len(fact) < 2:
                    continue
                if any(n in fact for n in NOISE):
                    continue
                if kind == "alias" and len(match.groups()) == 2:
                    left, right = _norm(match.group(1)), _norm(match.group(2))
                    if not left or not right or left == right:
                        continue
                    if left in ("我", "你", "他", "她", "它", "这", "那", "啥"):
                        continue
                    fact = f"{left} 叫 {right}"
                elif kind in ("name", "birthday", "like", "dislike"):
                    label = {
                        "name": "称呼",
                        "birthday": "生日",
                        "like": "喜欢",
                        "dislike": "不喜欢",
                    }[kind]
                    who = name or qq or "对方"
                    fact = f"{who} 的{label}：{fact}"
                if self._add(fact, kind, qq, name):
                    added.append(fact)
        if added:
            self.save()
        return added

    def _add(self, fact: str, kind: str, qq: str, name: str) -> bool:
        key = hashlib.md5(fact.encode("utf-8")).hexdigest()[:12]
        for item in self.facts:
            if item.get("key") == key:
                item["hits"] = int(item.get("hits", 1)) + 1
                item["ts"] = time.time()
                return False
        self.facts.append(
            {
                "key": key,
                "fact": fact,
                "kind": kind,
                "qq": qq,
                "name": name,
                "ts": time.time(),
                "hits": 1,
            }
        )
        return True

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        """按字符二元组重叠度召回，最多 limit 条。"""
        q = _bigrams(query)
        if not q:
            return []
        scored = []
        for item in self.facts:
            f = _bigrams(item.get("fact", ""))
            if not f:
                continue
            overlap = len(q & f)
            if overlap < 1:
                continue
            score = overlap / (len(q) ** 0.5 * len(f) ** 0.5)
            scored.append((score, item))
        scored.sort(key=lambda x: (x[0], x[1].get("hits", 1)), reverse=True)
        out = []
        for score, item in scored[:limit]:
            item["hits"] = int(item.get("hits", 1)) + 1
            out.append({**item, "score": round(score, 3)})
        if out:
            self.save()
        return out

    def recent(self, limit: int = 5) -> list[dict]:
        return sorted(self.facts, key=lambda f: f.get("ts", 0), reverse=True)[:limit]

    def stats(self) -> dict:
        kinds: dict[str, int] = {}
        for f in self.facts:
            kinds[f.get("kind", "?")] = kinds.get(f.get("kind", "?"), 0) + 1
        return {"total": len(self.facts), "kinds": kinds}

