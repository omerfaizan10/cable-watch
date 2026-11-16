# Cable Watch: every headline number is reproduced by these targets.
PY := .venv/bin/python
RAW := $(wildcard data/processed/raw_*.parquet)
RUNS := $(patsubst data/processed/raw_%.parquet,data/warehouse/run_gated_%.json,$(RAW)) \
        $(patsubst data/processed/raw_%.parquet,data/warehouse/run_agnostic_%.json,$(RAW))

.PHONY: setup data cables osm backfill warehouse eval test web dev redpanda-up kafka-check replay stream live live-check clean-runs

setup:            ## Python 3.12 venv and web deps
	uv venv --python 3.12 .venv && uv pip install --python $(PY) -r requirements.txt
	cd web && npm install

cables:           ## EMODnet cable and pipeline routes for the Baltic box (CC BY 4.0)
	$(PY) -m cablewatch.cables fetch

osm:              ## OpenStreetMap subsea cables (ODbL): pinned ways, then the bulk Overpass download (resumable)
	$(PY) -m cablewatch.cables fetch-osm-pinned
	$(PY) -m cablewatch.cables fetch-osm

data: cables osm  ## stream the DMA days used here (no raw zip is stored)
	scripts/fetch_all.sh

data/warehouse/run_gated_%.json: data/processed/raw_%.parquet
	$(PY) -m cablewatch.pipeline backfill $< --run gated_$*

data/warehouse/run_agnostic_%.json: data/processed/raw_%.parquet
	$(PY) -m cablewatch.pipeline backfill $< --run agnostic_$* --agnostic

backfill: $(RUNS) ## run the processor over every extracted day (use make -j4)

warehouse: backfill
	$(PY) -m cablewatch.pipeline warehouse

eval: warehouse   ## backtest + pipeline correctness checks, writes web/public/data/*.json
	$(PY) -m cablewatch.correctness
	$(PY) -m cablewatch.backtest
	$(PY) -m cablewatch.export_web
	cd web && node scripts/make-icons.mjs

test:
	$(PY) -m pytest -q tests

dev:
	cd web && npm run dev

# ---- streaming path (needs Docker for Redpanda; see README) ----
redpanda-up:
	docker compose up -d redpanda

kafka-check:      ## replay one day through Redpanda and check the stream equals the in-process run
	CABLEWATCH_BUS=kafka $(PY) -m cablewatch.kafka_check data/processed/raw_2022-02-25_26.parquet

replay:           ## play the Samus Swan window onto ais.raw at 120x real time with disorder
	$(PY) -m cablewatch.replay data/processed/raw_2022-02-25_26.parquet --speed 120 --jitter-ms 90000 --late-fraction 0.001

stream:
	$(PY) -m cablewatch.pipeline stream --run stream_demo

live:             ## aisstream.io consumer (needs AISSTREAM_API_KEY in .env)
	$(PY) -m cablewatch.live_aisstream

live-check:       ## listen to aisstream.io for 10 minutes and run the rows through the processor
	$(PY) -m cablewatch.live_aisstream --check 600

clean-runs:
	rm -f data/warehouse/run_*.json data/warehouse/alerts_*.parquet
