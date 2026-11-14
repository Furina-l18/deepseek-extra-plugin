"""影响核心 · 昼夜能量曲线（从省流插件抽取）。"""
from __future__ import annotations

from datetime import datetime
FAST_PROVIDER_DEFAULT = "deepseek/deepseek-flash"
PROVIDER_EXTRA_KEY = "selected_provider"

NODES = [
    (7 * 60 + 30, 10.0),
    (9 * 60 + 48, 20.0),
    (15 * 60 + 54, 70.0),
    (19 * 60 + 0, 100.0),
    (20 * 60 + 24, 70.0),
    (23 * 60 + 45, 20.0),
    (25 * 60 + 30, 10.0),  # 次日 01:30
]
SLEEP_START = 25 * 60 + 30
WAKE_MINUTE = 7 * 60 + 30
FLOOR = 10.0

SILENT_BELOW = 20.0
HALF_BELOW = 40.0
HALF_SKIP_RATE = 0.5


def _pchip_slopes(xs: list[float], ys: list[float]) -> list[float]:
    """Fritsch–Carlson 单调三次插值的节点斜率。"""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    delta = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0] = delta[0]
    m[-1] = delta[-1]
    for i in range(1, n - 1):
        if delta[i - 1] * delta[i] <= 0:
            m[i] = 0.0
        else:
            w1 = 2 * h[i] + h[i - 1]
            w2 = h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
    return m


_XS = [p[0] for p in NODES]
_YS = [p[1] for p in NODES]
_MS = _pchip_slopes(_XS, _YS)


def _hermite(x: float) -> float:
    lo, hi = 0, len(_XS) - 1
    if x <= _XS[0]:
        return _YS[0]
    if x >= _XS[-1]:
        return _YS[-1]
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if _XS[mid] <= x:
            lo = mid
        else:
            hi = mid
    h = _XS[hi] - _XS[lo]
    t = (x - _XS[lo]) / h
    h00 = 2 * t**3 - 3 * t**2 + 1
    h10 = t**3 - 2 * t**2 + t
    h01 = -2 * t**3 + 3 * t**2
    h11 = t**3 - t**2
    return (
        h00 * _YS[lo]
        + h10 * h * _MS[lo]
        + h01 * _YS[hi]
        + h11 * h * _MS[hi]
    )


def energy_at(dt: datetime) -> float:
    """返回当前能量百分比。01:30–07:30 固定 10%。"""
    minutes = dt.hour * 60 + dt.minute
    if minutes < 90:  # 00:00–01:30 属于前一天的下降段
        minutes += 24 * 60
    if minutes < WAKE_MINUTE or minutes > SLEEP_START:
        return FLOOR
    return _hermite(float(minutes))


def tier_of(energy: float) -> str:
    if energy < SILENT_BELOW:
        return "低（少量接话）"
    if energy < HALF_BELOW:
        return "偏低（主动接话减半）"
    if energy < 70:
        return "正常"
    return "高"


class EnergyModel:
    """昼夜基础曲线 + 配置化的接话率门控。"""

    def __init__(self, cfg: dict):
        self.silent_below = float(cfg.get("silent_below", SILENT_BELOW))
        self.half_below = float(cfg.get("half_below", HALF_BELOW))
        self.rate_40_70 = float(cfg.get("reply_rate_40_70", 0.5))
        self.rate_20_40 = float(cfg.get("reply_rate_20_40", 0.25))
        self.rate_10_20 = float(cfg.get("reply_rate_10_20", 0.05))
        self.rate_below_10 = float(cfg.get("reply_rate_below_10", 0.0))
        self.thinking_min = int(cfg.get("thinking_min_energy", 70))

    def base(self) -> float:
        return energy_at(datetime.now())

    def tier(self, value: float) -> str:
        return tier_of(value)

    def rate(self, value: float) -> float:
        if value < 10.0:
            return self.rate_below_10
        if value < self.silent_below:
            return self.rate_10_20
        if value < self.half_below:
            return self.rate_20_40
        if value < 70.0:
            return self.rate_40_70
        return 1.0
