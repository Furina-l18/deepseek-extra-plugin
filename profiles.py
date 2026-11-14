"""按人保存的情感画像，以及给激素/能量插件读取的偏置文件。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

try:
    from . import taxonomy
except ImportError:  # 单独测试
    import taxonomy  # type: ignore

BIAS_FILE = "emotion_bias.json"


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def energy_bias_for(profile: dict[str, Any]) -> float:
    """单个人的情感对能量的影响（含长期负面的稳态负荷）。"""
    dims = profile.get("dims") or {}
    sent = profile.get("sentiment") or {}
    score = float(sent.get("score", 0.0))
    samples = int(sent.get("samples", 1) or 1)
    arousal = float(dims.get("arousal", 0.0))
    chronic = max(0.0, -score) * min(1.0, samples / 30.0)
    return max(
        -20.0,
        min(20.0, (0.7 * score + 0.3 * arousal) * 12.0 - 6.0 * chronic),
    )


class ProfileStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.profiles_dir = data_dir / "profiles"
        self.bias_path = data_dir / BIAS_FILE

    # ------------------------------------------------------------ 画像

    def _path_of(self, qq: str) -> Path:
        safe = "".join(ch for ch in str(qq) if ch.isalnum() or ch in "-_") or "unknown"
        return self.profiles_dir / f"{safe}.json"

    def load(self, qq: str) -> dict[str, Any] | None:
        path = self._path_of(qq)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save(self, qq: str, profile: dict[str, Any]) -> None:
        _atomic_write(self._path_of(qq), profile)

    def list_all(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.profiles_dir.is_dir():
            return out
        for path in sorted(self.profiles_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict) and data.get("qq"):
                out.append(data)
        out.sort(key=lambda p: float(p.get("analyzed_at") or 0.0), reverse=True)
        return out

    # ------------------------------------------------------------ 偏置

    def write_bias(
        self,
        profile: dict[str, Any],
        weight: float,
        ttl_minutes: int,
    ) -> dict[str, Any]:
        emotions = profile.get("emotions") or {}
        top = sorted(
            ((k, float(v)) for k, v in emotions.items() if float(v) > 0),
            key=lambda kv: kv[1],
            reverse=True,
        )[:6]
        dims = profile.get("dims") or {}
        sent = profile.get("sentiment") or {}
        score = float(sent.get("score", 0.0))
        samples = int(sent.get("samples", 1) or 1)
        type_key = str(sent.get("type") or "")
        arousal = float(dims.get("arousal", 0.0))

        # 情感强度 → 神经化学偏移；情感越强，激素上的印记越深
        intensity = min(1.0, abs(score) * 1.6 + 0.2) if score else 0.0
        neuro = taxonomy.neurochem_for(type_key, intensity)

        # 稳态负荷：长期负面 + 观察得越久，对能量的拖累越大
        energy_bias = energy_bias_for(profile)

        bias = {
            "ts": time.time(),
            "ttl": max(60, int(ttl_minutes) * 60),
            "qq": profile.get("qq", ""),
            "name": profile.get("name", ""),
            "type": type_key,
            "dims": dims,
            "valence": float(dims.get("valence", 0.0)),
            "arousal": arousal,
            "affiliation": float(dims.get("affiliation", 0.0)),
            "top": top,
            "summary": profile.get("summary", ""),
            "keywords": list(profile.get("keywords") or [])[:5],
            "neuro": neuro,
            "energy_bias": round(energy_bias, 2),
            "weight": float(weight),
            "analyzed_at": profile.get("analyzed_at"),
        }
        _atomic_write(self.bias_path, bias)
        return bias

    def read_bias(self, ttl_minutes: int | None = None) -> dict[str, Any] | None:
        if not self.bias_path.is_file():
            return None
        try:
            data = json.loads(self.bias_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        ttl = data.get("ttl") or 1800
        if ttl_minutes is not None:
            ttl = max(60, int(ttl_minutes) * 60)
        if time.time() - float(data.get("ts", 0.0)) > float(ttl):
            return None
        return data

    def clear_bias(self) -> None:
        try:
            self.bias_path.unlink(missing_ok=True)
        except Exception:
            pass
