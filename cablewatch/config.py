"""All tunable thresholds in one place, so every number in an alert is traceable to a setting.

Defaults were chosen from published incident descriptions, not fitted to the backtest:
  * Eagle S slowed from about 12 kn to 9 kn when its anchor dropped, then kept falling
    (Finnish NBI findings, summarized on fi.wikipedia.org/wiki/Eagle_S).
  * Newnew Polar Bear dropped from 11 kn to about 6 kn at the Balticconnector crossing
    (ERR News, 2024-09-25).
  * Samus Swan crawled at 2.8 kn and then sat still with the engine at full power for over
    two hours while its anchor was down (TV 2 Bornholm, 2025-07-05, court record summary).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

MIN = 60_000


@dataclass(frozen=True)
class Config:
    # Geometry
    cable_buffer_m: float = 1_500.0  # fixes closer than this to a cable are "over the cable"
    landing_exclusion_m: float = 5_000.0  # ignore the approach to cable landing points (ports, shore)
    h3_res: int = 8

    # Streaming
    allowed_lateness_ms: int = 2 * MIN  # per-vessel event-time reorder bound

    # Data quality
    teleport_max_kn: float = 60.0  # implied speed above this between fixes is a bad fix
    teleport_min_dist_m: float = 500.0  # ignore jitter below this distance
    teleport_reset_after: int = 3  # consecutive rejects that agree with each other restart the track

    # Which vessels the rules evaluate (all vessels still pass data-quality accounting)
    mobile_types: tuple[str, ...] = ("Class A",)
    min_length_m: float = 50.0  # anchors that cut cables belong to large ships; unknown length is kept
    excluded_ship_types: tuple[str, ...] = (
        "Fishing", "Dredging", "Diving", "Military", "Law enforcement", "SAR", "Tug", "Pilot",
        "Port tender", "Towing", "Towing long/wide", "Anti-pollution", "Pleasure", "Sailing", "Medical",
    )
    excluded_nav_status: tuple[str, ...] = ("Moored",)

    # Rule: speed drop over a cable
    drop_baseline_window_ms: tuple[int, int] = (20 * MIN, 5 * MIN)  # [t-20min, t-5min]
    drop_recent_window_ms: int = 3 * MIN
    drop_min_baseline_kn: float = 7.0
    drop_max_ratio: float = 0.65
    drop_min_delta_kn: float = 3.0

    # Rule: loiter over a cable
    loiter_max_sog_kn: float = 3.0
    loiter_min_dwell_ms: int = 30 * MIN

    # Rule: anchor-drag signature (slow, erratic course, still moving)
    drag_window_ms: int = 20 * MIN
    drag_min_fixes: int = 6
    drag_sog_range_kn: tuple[float, float] = (0.5, 5.0)
    drag_min_cog_std_deg: float = 25.0
    drag_min_heading_cog_gap_deg: float = 30.0
    drag_min_displacement_m: float = 300.0

    # Rule: repeated crossing of the same cable. Tightened from 6 h after the first run on the
    # tuning day (2024-04-10): scheduled Rostock-Gedser ferries cross the Baltic Cable about
    # once an hour and tripped a 6 h window all day. A dragging ship zigzags back and forth
    # within tens of minutes. The tuning day is excluded from the false-alert measurement.
    cross_window_ms: int = 90 * MIN
    cross_min_count: int = 3
    cross_min_gap_ms: int = 5 * MIN  # crossings closer than this count once (parallel or wiggly route lines)

    # Alert de-duplication
    alert_cooldown_ms: int = 60 * MIN

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT = Config()
