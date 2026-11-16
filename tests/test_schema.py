from cablewatch.schema import RejectReason, mmsi_is_valid_ship, parse_dma_row, parse_dma_timestamp

ROW = {"# Timestamp": "26/02/2022 05:17:00", "Type of mobile": "Class A", "MMSI": "248363000",
       "Latitude": "55.123", "Longitude": "14.456", "Navigational status": "Under way using engine",
       "ROT": "0", "SOG": "2.8", "COG": "190.1", "Heading": "511", "IMO": "9401312", "Callsign": "9HA2333",
       "Name": "SAMUS SWAN", "Ship type": "Tanker", "Length": "106"}


def test_timestamp_is_utc_epoch_ms():
    assert parse_dma_timestamp("01/01/2024 00:00:00") == 1_704_067_200_000


def test_mmsi_validity():
    assert mmsi_is_valid_ship(219031008)
    assert not mmsi_is_valid_ship(2190310)  # too short
    assert not mmsi_is_valid_ship(111219000)  # SAR aircraft prefix
    assert not mmsi_is_valid_ship(992191234)  # AtoN
    assert not mmsi_is_valid_ship(100000000)


def test_parse_good_row_and_sentinels():
    p, r = parse_dma_row(ROW)
    assert r is None and p.mmsi == 248363000 and p.sog == 2.8 and p.heading is None and p.imo == "9401312"


def test_rejects():
    assert parse_dma_row({**ROW, "MMSI": "12345"})[1] == RejectReason.BAD_MMSI
    assert parse_dma_row({**ROW, "Latitude": "91"})[1] == RejectReason.BAD_LATLON
    assert parse_dma_row({**ROW, "Type of mobile": "Base Station"})[1] == RejectReason.NOT_A_SHIP
    assert parse_dma_row({**ROW, "# Timestamp": "yesterday"})[1] == RejectReason.BAD_TIMESTAMP


def test_sog_not_available():
    p, _ = parse_dma_row({**ROW, "SOG": "102.3", "COG": "360"})
    assert p.sog is None and p.cog is None
