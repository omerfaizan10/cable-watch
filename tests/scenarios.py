"""Hand-built vessel tracks around the unit-test cable (15.0 E). Not AIS data."""
import math

from conftest import MIN, T0, pos

M_PER_DEG_LAT = 111_195.0


def dlon_per_min(kn, lat):
    return kn * 1852 / 60 / (M_PER_DEG_LAT * math.cos(math.radians(lat)))


def dlat_per_min(kn):
    return kn * 1852 / 60 / M_PER_DEG_LAT


def eastbound_with_drop(mmsi=219000001, lat=55.1, start_lon=14.80, cruise=12.0, slow=4.0, t0=T0):
    """Cruise east at 12 kn, slow to 4 kn once within 1 km of the cable, keep going."""
    out, lon, t = [], start_lon, t0
    for _ in range(120):
        near = abs(lon - 15.0) < 0.016
        kn = slow if near or lon > 15.0 and lon < 15.03 else cruise
        out.append(pos(t, lat, round(lon, 6), sog=kn, cog=90.0, heading=90.0, mmsi=mmsi))
        lon += dlon_per_min(kn, lat)
        t += MIN
    return out


def straight_transit(mmsi=219000002, lat=55.2, t0=T0):
    out, lon, t = [], 14.85, t0
    for _ in range(90):
        out.append(pos(t, lat, round(lon, 6), sog=12.0, mmsi=mmsi))
        lon += dlon_per_min(12.0, lat)
        t += MIN
    return out


def loiter(mmsi=219000003, lat=55.15, lon=15.004, minutes=45, t0=T0, **kw):
    return [pos(t0 + i * MIN, lat, lon + (i % 3) * 1e-5, sog=0.8, cog=float((i * 7) % 360), heading=200.0,
                mmsi=mmsi, nav_status="At anchor", **kw) for i in range(minutes)]


def drag(mmsi=219000004, t0=T0):
    """Drift north along the cable at ~2 kn while the course swings +/- 60 deg."""
    out, lat, t = [], 55.05, t0
    for i in range(30):
        cog = (0 + (60 if i % 2 else -60)) % 360
        out.append(pos(t, round(lat, 6), 15.002, sog=2.0, cog=float(cog), heading=0.0, mmsi=mmsi))
        lat += dlat_per_min(2.0)
        t += MIN
    return out


def zigzag(mmsi=219000005, t0=T0):
    """Cross the cable back and forth every 20 minutes for 3 hours at 6 kn."""
    out, t = [], t0
    lat = 55.2
    lon = 14.99
    direction = 1
    for i in range(180):
        out.append(pos(t, round(lat, 6), round(lon, 6), sog=6.0, cog=90.0 if direction > 0 else 270.0,
                       heading=90.0 if direction > 0 else 270.0, mmsi=mmsi))
        lon += direction * dlon_per_min(6.0, lat)
        lat += dlat_per_min(1.0)
        if lon > 15.012 or lon < 14.988:
            direction *= -1
        t += MIN
    return out
