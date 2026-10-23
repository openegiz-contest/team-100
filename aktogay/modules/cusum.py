"""One-sided CUSUM on standardised residuals with a fast one-cycle threshold.

Evidence map (file 19), section 3 B: instead of "2 sigma three cycles in a
row" the detector is a one-sided CUSUM on z = gap / sigma with reference
k = 0.5 and decision interval h about 6.5 (six monitors), plus a fast
threshold z >= 3.5 in a single cycle. NIST/SEMATECH e-Handbook 6.3.2.3.

  S_n = max(0, S_(n-1) + z_n - k);  alarm when S_n >= h or z_n >= fast.

The alarm is latched: it stays until S falls back to 0 (the gap has gone
for a while). S is capped at 2 h so a long-lasting cause clears within a
few cycles after it ends. Only positive gaps (losses) are tracked: a node
doing better than expected is not an issue.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CusumState:
    s: float = 0.0            # cumulative sum
    alarm: bool = False       # latched alarm
    n: int = 0                # updates seen
    last_z: float = 0.0
    fired_n: int = -1         # update index at which the alarm fired (-1: never)
    fired_by: str = ""        # "cusum" | "fast"
    history: list[float] = field(default_factory=list)   # last z values (bounded)


class OneSidedCusum:
    """Detector of an upward shift in z; see the module docstring."""

    def __init__(self, k: float = 0.5, h: float = 6.5, fast: float = 3.5, keep: int = 12):
        if h <= 0.0 or fast <= 0.0:
            raise ValueError("h and fast must be positive")
        self.k, self.h, self.fast, self.keep = float(k), float(h), float(fast), int(keep)
        self.st = CusumState()

    def reset(self) -> None:
        self.st = CusumState()

    def update(self, z: float) -> bool:
        """Feed one standardised residual; returns the alarm state after it."""
        st = self.st
        st.n += 1
        st.last_z = float(z)
        st.history.append(float(z))
        if len(st.history) > self.keep:
            del st.history[: len(st.history) - self.keep]
        st.s = min(max(0.0, st.s + z - self.k), 2.0 * self.h)
        if not st.alarm:
            if z >= self.fast:
                st.alarm, st.fired_n, st.fired_by = True, st.n, "fast"
            elif st.s >= self.h:
                st.alarm, st.fired_n, st.fired_by = True, st.n, "cusum"
        elif st.s <= 0.0:
            st.alarm, st.fired_n, st.fired_by = False, -1, ""
        return st.alarm

    @property
    def alarm(self) -> bool:
        return self.st.alarm

    @property
    def s(self) -> float:
        return self.st.s


def z_score(gap: float, sigma: float) -> float:
    """gap / sigma; 0 when sigma is not positive."""
    return gap / sigma if sigma > 0.0 else 0.0


def status_of(z: float, alarm: bool, unsure_z: float = 2.0) -> str:
    """Node status code: 'loss' (alarm), 'unsure' (|z| >= unsure_z, no alarm), 'noise' (inside noise)."""
    if alarm:
        return "loss"
    if abs(z) >= unsure_z:
        return "unsure"
    return "noise"


STATUS_RU = {
    "loss": "потеря",
    "unsure": "не уверен",
    "noise": "в пределах шума",
    "idle": "узел стоит",
    "feed": "ограничено питанием",
    "no_data": "нет данных",
}
