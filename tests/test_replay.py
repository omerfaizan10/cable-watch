from cablewatch.replay import arrival_schedule


def rows(n):
    return [{"# Timestamp": f"01/01/2024 00:{i // 60:02d}:{i % 60:02d}", "MMSI": "219000001"} for i in range(n)]


def test_schedule_is_reproducible_and_bounded():
    a = arrival_schedule(rows(600), jitter_ms=90_000, late_fraction=0.0, lateness_ms=120_000, seed=3)
    b = arrival_schedule(rows(600), jitter_ms=90_000, late_fraction=0.0, lateness_ms=120_000, seed=3)
    assert [x[1] for x in a] == [x[1] for x in b]
    assert [x[1] for x in a] != list(range(600))  # it really reorders
    assert not any(x[3] for x in a)


def test_injected_late_rows_exceed_bound():
    s = arrival_schedule(rows(2000), jitter_ms=0, late_fraction=0.05, lateness_ms=120_000, seed=1)
    late = [x for x in s if x[3]]
    assert 50 < len(late) < 150
    from cablewatch.schema import parse_dma_timestamp
    for arr, _, row, _ in late:
        assert arr - parse_dma_timestamp(row["# Timestamp"]) > 120_000
