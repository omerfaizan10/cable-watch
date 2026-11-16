"""Shared helpers. Every fixture here is hand-built test geometry, not AIS data."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from cablewatch.config import Config
from cablewatch.geo import Cable, CableIndex
from cablewatch.schema import Position

T0 = 1_700_000_000_000
MIN = 60_000

# A straight north-south test cable at 15.0 E from 54.8 N to 55.4 N.
TEST_CABLE = Cable("test#0", "Test cable", "power", "unit-test fixture", [(54.8, 15.0), (55.4, 15.0)])


@pytest.fixture
def cfg():
    return Config()


@pytest.fixture
def index(cfg):
    return CableIndex.build([TEST_CABLE], cfg.cable_buffer_m, cfg.h3_res)


def pos(ts, lat, lon, sog=10.0, cog=90.0, heading=90.0, mmsi=219000001, **kw):
    d = dict(ts=ts, mmsi=mmsi, lat=lat, lon=lon, sog=sog, cog=cog, heading=heading, nav_status="Under way using engine",
             mobile_type="Class A", imo="9000001", name="TEST VESSEL", ship_type="Cargo", length=150.0)
    d.update(kw)
    return Position(**d)
