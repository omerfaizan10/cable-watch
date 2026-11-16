"""Canonical AIS position record and parsing/validation of Danish Maritime Authority rows.

DMA CSV columns are documented in the archive README
(http://aisdata.ais.dk/!_README_information_CSV_files.txt):
  # Timestamp, Type of mobile, MMSI, Latitude, Longitude, Navigational status, ROT,
  SOG, COG, Heading, IMO, Callsign, Name, Ship type, Cargo type, Width, Length,
  Type of position fixing device, Draught, Destination, ETA, Data source type, A, B, C, D
Timestamps are UTC in the form 31/12/2015 23:59:59.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

# AIS sentinel values meaning "not available" (ITU-R M.1371).
SOG_NA = 102.3
COG_NA = 360.0
HEADING_NA = 511

# Maritime Identification Digits for ship stations are 201 to 775 (ITU-R M.585).
MID_MIN, MID_MAX = 201, 775


@dataclass(frozen=True, slots=True)
class Position:
    ts: int  # event time, epoch milliseconds UTC
    mmsi: int
    lat: float
    lon: float
    sog: float | None  # knots
    cog: float | None  # degrees true
    heading: float | None  # degrees true
    nav_status: str
    mobile_type: str
    imo: str
    name: str
    ship_type: str
    length: float | None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Position":
        return Position(**d)

    def sort_key(self) -> tuple:
        # Total order used everywhere: event time, then the fields that break ties
        # deterministically when two fixes share a timestamp.
        n = lambda v: -1.0 if v is None else v  # noqa: E731
        return (self.ts, self.mmsi, self.lat, self.lon, n(self.sog), n(self.cog), n(self.heading),
                self.nav_status, self.mobile_type, self.imo, self.name, self.ship_type, n(self.length))


class RejectReason:
    BAD_TIMESTAMP = "bad_timestamp"
    BAD_MMSI = "invalid_mmsi"
    BAD_LATLON = "lat_lon_out_of_range"
    NOT_A_SHIP = "not_class_a_or_b_vessel"
    PARSE_ERROR = "parse_error"


_DAY_CACHE: dict[str, int] = {}


def parse_dma_timestamp(s: str) -> int:
    """'dd/mm/YYYY HH:MM:SS' (UTC) to epoch ms. The date part is cached because a day file
    has millions of rows and one date."""
    s = s.strip()
    if len(s) != 19 or s[2] != "/" or s[5] != "/" or s[13] != ":" or s[16] != ":":
        raise ValueError(f"bad DMA timestamp {s!r}")
    day = s[:10]
    base = _DAY_CACHE.get(day)
    if base is None:
        dt = datetime.strptime(day, "%d/%m/%Y").replace(tzinfo=timezone.utc)
        base = _DAY_CACHE[day] = int(dt.timestamp() * 1000)
    h, m, sec = int(s[11:13]), int(s[14:16]), int(s[17:19])
    if h > 23 or m > 59 or sec > 60:
        raise ValueError(f"bad DMA timestamp {s!r}")
    return base + (h * 3600 + m * 60 + sec) * 1000


def mmsi_is_valid_ship(mmsi: int) -> bool:
    """A ship station MMSI is 9 digits with a leading MID of 201 to 775."""
    if not (100_000_000 <= mmsi <= 999_999_999):
        return False
    mid = mmsi // 1_000_000
    return MID_MIN <= mid <= MID_MAX


def _f(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def parse_dma_row(row: dict) -> tuple[Position | None, str | None]:
    """Parse one DMA CSV row (dict keyed by header). Returns (position, reject_reason)."""
    try:
        ts_raw = row.get("# Timestamp") or row.get("Timestamp") or ""
        try:
            ts = parse_dma_timestamp(ts_raw)
        except ValueError:
            return None, RejectReason.BAD_TIMESTAMP
        mobile = (row.get("Type of mobile") or "").strip()
        if mobile not in ("Class A", "Class B"):
            return None, RejectReason.NOT_A_SHIP
        try:
            mmsi = int((row.get("MMSI") or "").strip())
        except ValueError:
            return None, RejectReason.BAD_MMSI
        if not mmsi_is_valid_ship(mmsi):
            return None, RejectReason.BAD_MMSI
        lat, lon = _f(row.get("Latitude")), _f(row.get("Longitude"))
        if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None, RejectReason.BAD_LATLON
        if lat == 0 and lon == 0:
            return None, RejectReason.BAD_LATLON
        # DMA uses 91/181 as "not available" in some rows.
        if abs(lat) > 90 or abs(lon) > 180 or lat == 91 or lon == 181:
            return None, RejectReason.BAD_LATLON
        sog = _f(row.get("SOG"))
        if sog is not None and (sog < 0 or sog >= SOG_NA):
            sog = None
        cog = _f(row.get("COG"))
        if cog is not None and (cog < 0 or cog >= COG_NA):
            cog = None
        hdg = _f(row.get("Heading"))
        if hdg is not None and (hdg < 0 or hdg >= 360):
            hdg = None
        imo = (row.get("IMO") or "").strip()
        if imo in ("Unknown", "0"):
            imo = ""
        return (
            Position(
                ts=ts,
                mmsi=mmsi,
                lat=round(lat, 6),
                lon=round(lon, 6),
                sog=sog,
                cog=cog,
                heading=hdg,
                nav_status=(row.get("Navigational status") or "").strip(),
                mobile_type=mobile,
                imo=imo,
                name=(row.get("Name") or "").strip(),
                ship_type=(row.get("Ship type") or "").strip(),
                length=_f(row.get("Length")),
            ),
            None,
        )
    except Exception:  # noqa: BLE001 (any malformed row is counted, never fatal)
        return None, RejectReason.PARSE_ERROR
