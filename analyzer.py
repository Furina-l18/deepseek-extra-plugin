"""情感总结：调用本地 Ollama，失败时退回关键词估计。"""

from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.request
from typing import Any

try:  # 插件内以包方式导入
    from .taxonomy import (
        DIM_KEYS,
        EMOTION_TYPES,
        EVENT_WEIGHTS,
        KEYWORD_LEXICON,
        TYPE_CENTERS,
        clamp,
        empty_emotions,
    )
except ImportError:  # 单独测试时以顶层模块导入
    from taxonomy import (  # type: ignore
        DIM_KEYS,
        EMOTION_TYPES,
        EVENT_WEIGHTS,
        KEYWORD_LEXICON,
        TYPE_CENTERS,
        clamp,
        empty_emotions,
    )

_NOISE = re.compile(r"\[(图片|表情|语音|视频|文件|回复[^\]]*)\]")
_THINK = re.compile(r"<think\b[^>]*>.*?<｜end▁of▁thinking｜>", re.S | re.I)

SYSTEM_PROMPT = (
    "你在模仿一个人类的情感。分析对象是一个聊天机器人（下面称「它」）。\n"
    "你会读到它和某个人过往的聊天记录。请回答：这些互动让**它**对这个人产生了什么情感。\n"
    "\n"
    "情感要像人一样，由**具体发生的事**触发，而不是由聊天多少决定：\n"
    "- 被夸奖、被感谢、被关心 → 它会开心、愉悦、亲近；\n"
    "- 被辱骂、被嫌弃、被冷落、被敷衍 → 它会伤心、难受、委屈、生气；\n"
    "- 只是普通闲聊、没有明显好恶 → 情感不变（这是最常见的情况）。\n"
    "特别注意：聊了很多句不等于正面情感，聊得少也不等于负面情感。\n"
    "\n"
    "只根据聊天内容推断，不要编造。输出必须是纯 JSON，不要任何解释、不要代码块。\n"
    "JSON 结构：\n"
    "{\n"
    '  "impact": {"kind": "insult", "intensity": 0.8},\n'
    '  "emotions": [{"name": "委屈", "intensity": 0.8}, {"name": "亲近", "intensity": 0.5}],\n'
    '  "summary": "两三句话描述机器人对这个人的情感，以及是什么事造成的",\n'
    '  "keywords": ["支撑判断的关键词", "..."]\n'
    "}\n"
    "impact 是对方对它做的、最主要的那一件事，kind 只能取："
    + "、".join(EVENT_WEIGHTS.keys())
    + "；\n"
    "  如果只是普通闲聊、没有明显的夸奖或辱骂，就用 kind=chat、intensity=0.1"
    "（chat 不改变情感）。\n"
    "  intensity 0.1~1 表示这件事的冲击强度。\n"
    "emotions 是**它自己的感受**（不是对方的心情），写 2 到 4 条，按强度从高到低；\n"
    "  name 只能从这份清单里选：" + "、".join(EMOTION_TYPES) + "。\n"
    "intensity 取 0~1：0.9-1.0 极强烈、0.6-0.8 明显、0.3-0.5 轻微，不要一律写 1。\n"
    "summary 要具体，提到是什么事造成的。keywords 最多 5 个，不要重复同一个词。"
)

# 让 Ollama 用语法约束生成，避免小模型把 JSON 结构写坏。
# 注意：不让模型输出八维——小模型写数值极不稳定，改由情绪标签在本地推导。
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "impact": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(EVENT_WEIGHTS)},
                "intensity": {"type": "number", "minimum": 0.1, "maximum": 1},
            },
            "required": ["kind", "intensity"],
        },
        "emotions": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": EMOTION_TYPES},
                    "intensity": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["name", "intensity"],
            },
        },
        "summary": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["impact", "emotions", "summary", "keywords"],
}


def _clean(text: str) -> str:
    text = _NOISE.sub(" ", text or "")
    return re.sub(r"\s+", " ", text).strip()


_JUNK_EXACT = {"无聊天记录", "无法推断", "无法判断", "无内容", "未提及", "没有内容", "请分析", "...", "……", "无"}
_JUNK_PARTS = ("无聊天", "无法推断", "无法判断", "无内容", "未提及", "没有内容", "请分析")


def _is_junk_keyword(text: str) -> bool:
    """过滤模型在没材料时爱写的占位词。"""
    k = (text or "").strip()
    if not k or k in _JUNK_EXACT:
        return True
    return any(part in k for part in _JUNK_PARTS)


def build_material(
    name: str, contents: list[str], max_chars: int = 6000, prior: str = ""
) -> str:
    """把聊天记录压成一段材料，从最近的往前取，控制总长度。

    prior 是此前已经推理过的旧档案摘要：只作背景参考，不让模型重复推理。
    """
    picked: list[str] = []
    used = 0
    for text in reversed(contents):
        c = _clean(text)
        if not c:
            continue
        if used + len(c) > max_chars and picked:
            break
        picked.append(c)
        used += len(c)
    picked.reverse()
    body = "\n".join(f"- {c}" for c in picked)
    head = ""
    if prior.strip():
        head = (
            "背景（此前已经整理过，只作参考，不要重新推理、不要计入本轮情绪）：\n"
            f"{prior.strip()}\n\n"
        )
    return f"{head}以下是「{name}」这一轮新的聊天发言（按时间正序）：\n{body}"


def list_models(base_url: str, timeout: float = 5.0) -> list[str]:
    """列出 Ollama 里已有的模型名。"""
    try:
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return [
            str(m.get("name") or "")
            for m in (data.get("models") or [])
            if isinstance(m, dict) and m.get("name")
        ]
    except Exception:
        return []


def call_ollama(
    base_url: str,
    model: str,
    prompt: str,
    timeout: float = 180.0,
) -> str:
    """同步调用 Ollama /api/chat，返回模型文本。调用方负责放到线程里跑。"""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": RESPONSE_SCHEMA,
        "keep_alive": "30m",
        "options": {"temperature": 0.2, "num_predict": 3000, "repeat_penalty": 1.35},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
    obj = json.loads(raw)
    return str((obj.get("message") or {}).get("content") or "")


def unload_model(base_url: str, model: str, timeout: float = 15.0) -> bool:
    """让 Ollama 立刻把模型从显存里卸掉（keep_alive=0），返回是否成功。

    Ollama 的约定：/api/generate 带空 prompt + keep_alive=0 时只做卸载，不产生推理。
    """
    payload = {"model": model, "keep_alive": 0}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            resp.read()
        return True
    except Exception:
        return False


def running_models(base_url: str, timeout: float = 5.0) -> list[str]:
    """列出当前驻留在内存/显存里的模型名。"""
    try:
        with urllib.request.urlopen(  # noqa: S310
            f"{base_url.rstrip('/')}/api/ps", timeout=timeout
        ) as resp:
            obj = json.loads(resp.read().decode("utf-8", errors="replace"))
        return [
            str(m.get("name") or m.get("model") or "")
            for m in (obj.get("models") or [])
            if isinstance(m, dict)
        ]
    except Exception:
        return []


def _iter_json_objects(text: str):
    """找出文本里所有配平的 {...} 片段。"""
    depth = 0
    start = -1
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    yield text[start : i + 1]
                    start = -1


def parse_model_json(text: str) -> dict[str, Any] | None:
    """从模型输出里抠出可用的 JSON。"""
    if not text:
        return None
    cleaned = _THINK.sub("", text)
    cleaned = cleaned.replace("```json", "```").strip()
    for blob in _iter_json_objects(cleaned):
        try:
            obj = json.loads(blob)
        except Exception:
            continue
        if isinstance(obj, dict) and ("dims" in obj or "emotions" in obj):
            return obj
    # 输出被截断时（小模型偶尔会把 keywords 写成一长串重复词）单独抢救字段
    return _salvage_json(cleaned)


def _extract_object(text: str, key: str) -> dict | None:
    """从 key 后面抓第一个配平的 {...}。"""
    idx = text.find(f'"{key}"')
    if idx < 0:
        return None
    start = text.find("{", idx)
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except Exception:
                    return None
    return None


def _extract_array(text: str, key: str) -> list | None:
    """从 key 后面抓第一个配平的 [...]。"""
    idx = text.find(f'"{key}"')
    if idx < 0:
        return None
    start = text.find("[", idx)
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except Exception:
                    return None
    return None


def _salvage_emotions(text: str) -> list[dict[str, Any]]:
    """输出被截断时，逐个对象抢救 {name, intensity}。"""
    items: list[dict[str, Any]] = []
    for m in re.finditer(r"\{[^{}]*\}", text):
        blob = m.group(0)
        if '"name"' not in blob or '"intensity"' not in blob:
            continue
        n = re.search(r'"name"\s*:\s*"([^"]+)"', blob)
        v = re.search(r'"intensity"\s*:\s*(-?[0-9.eE+]+)', blob)
        if not n or not v:
            continue
        try:
            items.append({"name": n.group(1), "intensity": float(v.group(1))})
        except ValueError:
            continue
    return items


def _salvage_json(text: str) -> dict[str, Any] | None:
    """JSON 被截断时，分别抢救 dims / emotions / summary / keywords。"""
    out: dict[str, Any] = {}

    dims = _extract_object(text, "dims")
    if dims:
        out["dims"] = dims

    emotions = _extract_array(text, "emotions")
    if isinstance(emotions, list) and emotions:
        out["emotions"] = emotions
    else:
        pairs = _salvage_emotions(text)
        if pairs:
            out["emotions"] = pairs
        else:
            obj = _extract_object(text, "emotions")
            if obj and any(k in EMOTION_TYPES for k in obj):
                out["emotions"] = obj

    if not out:
        return None

    m = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if m:
        try:
            out["summary"] = json.loads(f'"{m.group(1)}"')
        except Exception:
            out["summary"] = m.group(1)
    m2 = re.search(r'"keywords"\s*:\s*\[((?:[^\]\\]|\\.)*)', text)
    if m2:
        words = re.findall(r'"((?:[^"\\]|\\.)*)"', m2.group(1))
        out["keywords"] = words[:5]
    return out


def _num(value: Any, default: float = 0.0) -> float:
    """把模型给的任何东西安全转成有限浮点。"""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(f):
        return default
    return f


def normalize(raw: dict[str, Any] | None, fallback_summary: str = "") -> dict[str, Any] | None:
    """把模型结果收敛到固定结构。"""
    if not raw:
        return None
    dims_in = raw.get("dims") if isinstance(raw.get("dims"), dict) else {}
    model_dims = {k: clamp(_num(dims_in.get(k, 0.0))) for k in DIM_KEYS}
    has_model_dims = bool(dims_in)

    emotions = empty_emotions()
    emo_in = raw.get("emotions")
    pairs: list[tuple[Any, Any]] = []
    if isinstance(emo_in, dict):
        pairs = list(emo_in.items())
    elif isinstance(emo_in, list):
        for item in emo_in:
            if isinstance(item, dict):
                pairs.append((item.get("name"), item.get("intensity")))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                pairs.append((item[0], item[1]))
    for name, value in pairs:
        if name in emotions:
            emotions[name] = max(0.0, min(1.0, _num(value, 0.0)))

    summary = str(raw.get("summary") or fallback_summary or "").strip()[:400]
    keywords = [
        str(k).strip()
        for k in (raw.get("keywords") or [])
        if str(k).strip() and not _is_junk_keyword(str(k))
    ][:12]

    if not any(emotions.values()):
        # 模型没给任何有效情绪：不要用零维度瞎猜，交给调用方重试或走关键词兜底
        return None

    # 小模型经常把维度符号写反（例如「疲惫 0.8」却给 fatigue −0.5）。
    # 用情绪反推一组维度，和模型自报的维度融合，保证两者自洽。
    derived = _dims_from_emotions(emotions)
    if has_model_dims:
        # 模型自报了维度：与情绪推导结果融合，修正小模型的符号错误
        dims = {k: clamp(0.45 * model_dims[k] + 0.55 * derived[k]) for k in DIM_KEYS}
    else:
        # 常规路径：八维完全由情绪标签推导，保证自洽
        dims = {k: clamp(derived[k] * 1.15) for k in DIM_KEYS}

    if not summary:
        top = sorted(
            ((k, v) for k, v in emotions.items() if v > 0),
            key=lambda kv: kv[1],
            reverse=True,
        )[:3]
        names = "、".join(k for k, _ in top) or "平静"
        summary = f"主要情绪：{names}（愉悦 {dims['valence']:+.2f}）"

    events: list[dict[str, Any]] = []

    def _push_event(item: Any) -> None:
        if not isinstance(item, dict):
            return
        kind = str(item.get("kind") or "")
        if kind not in EVENT_WEIGHTS:
            return
        inten = _num(item.get("intensity", 0.0))
        if inten < 0.05:
            return
        events.append({"kind": kind, "intensity": round(max(0.0, min(1.0, inten)), 3)})

    _push_event(raw.get("impact"))
    ev_in = raw.get("events")
    if isinstance(ev_in, list):
        for item in ev_in:
            _push_event(item)

    return {
        "dims": dims,
        "emotions": emotions,
        "events": events,
        "summary": summary,
        "keywords": keywords,
        "confidence": 0.6,
        "engine": "ollama",
    }


def dims_from_emotions(emotions: dict[str, float]) -> dict[str, float]:
    """按情绪标签推导八维（公开版，给增量合并用）。"""
    return {k: clamp(v * 1.15) for k, v in _dims_from_emotions(emotions).items()}


def _dims_from_emotions(emotions: dict[str, float]) -> dict[str, float]:
    """按情绪强度加权平均各情绪的中心维度，并按平均强度缩放。

    强度不能被归一化掉：一条 intensity=0.5 的「疲惫」不该顶出满格 fatigue。
    """
    acc = {k: 0.0 for k in DIM_KEYS}
    total = 0.0
    count = 0
    for name, intensity in emotions.items():
        if intensity <= 0:
            continue
        center = TYPE_CENTERS.get(name)
        if not center:
            continue
        for k in DIM_KEYS:
            acc[k] += center[k] * intensity
        total += intensity
        count += 1
    if total > 0:
        avg = total / max(1, count)
        for k in DIM_KEYS:
            acc[k] = acc[k] / total * avg
    return acc


def _emotions_from_dims(dims: dict[str, float]) -> dict[str, float]:
    """模型没给情绪时，按维度距离把最接近的几种挑出来。"""
    scored: list[tuple[float, str]] = []
    for name, center in TYPE_CENTERS.items():
        dist = sum((dims[k] - center[k]) ** 2 for k in DIM_KEYS) / len(DIM_KEYS)
        scored.append((dist, name))
    scored.sort()
    out = empty_emotions()
    for i, (dist, name) in enumerate(scored[:5]):
        out[name] = max(0.05, 0.8 - i * 0.15)
    return out


def fallback_analyze(contents: list[str]) -> dict[str, Any]:
    """无模型时按关键词给一个粗糙但方向正确的估计。"""
    hits = {name: 0 for name in EMOTION_TYPES}
    total = 0
    for text in contents:
        c = _clean(text)
        for name, words in KEYWORD_LEXICON.items():
            for w in words:
                if w and w in c:
                    hits[name] += 1
                    total += 1
    emotions = empty_emotions()
    if total:
        top = sorted(hits.items(), key=lambda kv: kv[1], reverse=True)
        peak = max(1, top[0][1])
        for name, n in top[:6]:
            if n <= 0:
                continue
            emotions[name] = max(0.08, min(1.0, (n / peak) * 0.75))
    else:
        emotions["平静"] = 0.4

    dims = {k: 0.0 for k in DIM_KEYS}
    weight_sum = 0.0
    for name, intensity in emotions.items():
        if intensity <= 0:
            continue
        center = TYPE_CENTERS[name]
        for k in DIM_KEYS:
            dims[k] += center[k] * intensity
        weight_sum += intensity
    if weight_sum > 0:
        for k in DIM_KEYS:
            dims[k] = clamp((dims[k] / weight_sum) * 0.8)

    top_names = [n for n, v in sorted(emotions.items(), key=lambda kv: kv[1], reverse=True) if v > 0][:3]
    return {
        "dims": dims,
        "emotions": emotions,
        "events": [],
        "summary": "（本地模型不可用时由关键词估计）主要情绪：" + "、".join(top_names),
        "keywords": top_names,
        "confidence": 0.35,
        "engine": "fallback",
    }
