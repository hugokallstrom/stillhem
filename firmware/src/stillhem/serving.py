"""Heuristic for whether the LAN's DNS is pointed at this device.

Traffic-volume signal, NOT a device count: an idle appliance resolves almost
nothing, so query volume jumps once the router points the LAN's DNS at the Pi.
"""

SERVING_QPM_THRESHOLD = 3.0


def queries_per_minute(prev_ts: float, prev_count: int, cur_ts: float, cur_count: int) -> float:
    elapsed = cur_ts - prev_ts
    if elapsed <= 0:
        return 0.0
    delta = cur_count - prev_count
    if delta < 0:  # counter reset (Unbound restarted) — no usable signal
        return 0.0
    return delta / elapsed * 60.0


def is_serving(qpm: float) -> bool:
    return qpm >= SERVING_QPM_THRESHOLD
