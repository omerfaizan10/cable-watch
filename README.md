# Cable Watch

Since 2022 a run of subsea power and telecom cables in the Baltic has been cut, and in most of the cases that were investigated a ship had dragged its anchor across them. Cable Watch is a streaming pipeline that replays Danish Maritime Authority ship positions (AIS), watches for ships behaving like they are dragging an anchor over a mapped cable, and grades itself against every publicly reported break the data can test.

Live site: https://cable-watch.vercel.app

## Results

**The data.** 30 days of the DMA archive for the western Baltic (9.5 to 24 E, 53.5 to 60.5 N), 429,598,973 position reports in total: the 36 hours around the 2022 Bornholm cable failure, four days with reported breaks in 2024 and 2025, one tuning day, and 24 ordinary days. Four of the ordinary days were chosen before any results existed; the rest are drawn at random from the daily files, 2 or 3 per month from March 2024 to February 2025 and never within a day of a reported incident (`scripts/pick_normal_days.py`, seeded, 30 days in the list; the last few are still being added). Cable routes: 824 from EMODnet plus the Bornholm cable from OpenStreetMap, which EMODnet lacks. Every run ends with a ledger that has to balance: each row read is accounted for as accepted, rejected (with a reason), an exact duplicate, a bad position, or late.

**Eight reported incidents, one fair test.** For each incident in `data/reference/incidents.csv` (sources cited per row) the backtest decides from the data whether it can be tested at all. Most cannot: the named ship never comes into Danish receiver range (the measured range ends near 18.6 E, short of eastern Gotland and the Gulf of Finland), it only appears after the break, the break is after the public archive ends (February 2025), or only the date of the break was published. One is testable: Samus Swan and the Bornholm power cable, 26 February 2022, 05:17 UTC.

**The behavior rules missed it.** Samus Swan crossed the cable at a steady 9.6 knots on a straight course. The Danish court later found its anchor had been dragging for about 35 hours, but nothing in its speed or course looked unusual at the moment of the break, so none of the four rules (sharp slowdown, slow dwell, sideways drift, repeated crossing) could fire. I report that as a miss.

**Timing and position found it.** Listing every ship that crossed the Bornholm cable within four hours of the failure and ranking them by how close the crossing came to 05:17 puts Samus Swan first of 51. It crossed 3.1 minutes after the reported time, at a point 16.7 km from the Swedish landing; the operator, Energinet, reported the break 17 km from Sweden. The next ship crossed 14.5 minutes off, so this only works because the failure time was published to the minute. The route itself is missing from EMODnet, the EU's cable data, and comes from OpenStreetMap.

**Cable map versus whole sea.** On the 24 ordinary days, the rules raise a median of 34.5 alerts a day when they only watch mapped cables (mean 43; 8 days in 10 between 13 and 86), and a median of 1,675 when they watch the whole sea. Both figures come from the same days. Every alert on those days is counted as false, which overstates the problem: survey and cable-work vessels really do loiter over cables.

**The pipeline gives the same answer in any order.** Replaying the Samus Swan window in three random arrival orders, and again with 2,862 rows pushed past the lateness bound, gives exactly the same alerts as the in-order run. The full 36-hour file (11,089,027 rows) was also run through Redpanda, a Kafka-API broker, with a 6-partition topic keyed by ship: every row was consumed, the ledger balanced, and the alerts matched an in-process run over the same rows in the same order (`make kafka-check`, result in `data/warehouse/kafka_check.json`).

## How it works

1. **Extract.** `cablewatch/dma_archive.py` streams the DMA daily (or monthly) zip, never storing it, and keeps rows inside the bounding box as Parquet. It also records how many fixes each 0.2 degree cell received, which is how the receiver range above was measured.
2. **Replay.** `cablewatch/replay.py` plays a day onto the `ais.raw` topic in event-time order with a seeded arrival model: every row is delayed by up to 90 s, and a set fraction is delayed past the lateness bound on purpose.
3. **Process.** `cablewatch/engine.py` keeps per-ship state. It reorders each ship's fixes by event time within 120 s, drops exact duplicates (one message heard by several stations), holds back positions that imply more than 60 knots unless three in a row agree, and runs the rules in `cablewatch/rules.py` on fixes within 1.5 km of a cable (an H3 index finds the candidate cable segments per fix). Alerts go to the `cable.alerts` topic and to Parquet; late rows go to `ais.late`.
4. **Bus.** `cablewatch/bus.py` has two implementations behind one interface: Redpanda through `confluent-kafka`, and an embedded append-only log so everything runs without Docker.
5. **Warehouse and backtest.** DuckDB reads the alert Parquet and run audits. `cablewatch/backtest.py` scores incidents and ordinary days and runs the outage lookup; `cablewatch/correctness.py` runs the ordering and late-data checks.
6. **Live.** `cablewatch/live_aisstream.py` converts the aisstream.io WebSocket feed into the same row shape, so live data uses every line of processing code after it. It needs a free key and the site never depends on it. A 10-minute check (`make live-check`, 15 November 2026) received 3,806 position reports from 1,976 ships with a median delay of 3.5 s, and the ledger balanced. The free feed is sparse, though: a median of 2 reports per ship in 10 minutes, against 7 in the Danish archive for a 10-minute window (48,121 reports from 1,563 ships on 12 February 2025, 10:00 to 10:10 UTC). At that rate the rules rarely have enough fixes to fire, so live mode proves the plumbing, not the detection.
7. **Site.** `cablewatch/export_web.py` precomputes small JSON files; the Next.js site in `web/` draws them with MapLibre and SVG, so nothing is computed in the browser except drawing. It is laid out as a report: a summary, then pages for the replay, the incidents (one page per incident, with sources), false alerts, the pipeline and its checks, the method, and a plain-language explainer.

Every threshold lives in `cablewatch/config.py` with the published incident description it came from. One setting was changed after looking at data: the repeated-crossing window went from 6 hours to 90 minutes because scheduled ferries tripped it on the tuning day (2024-04-10), which is why that day is excluded from the false-alert rate.

## Running it

Requirements: [uv](https://docs.astral.sh/uv/), Node 20 or newer, and Docker only for the Kafka path.

```
make setup          # Python 3.12 venv and web dependencies
make data           # cable routes (EMODnet, pinned OpenStreetMap ways) and the DMA days (zips are streamed, not stored; the kept Parquet is about 3 GB)
make -j4 backfill   # cable-gated and cable-agnostic runs for every day
make eval           # warehouse, correctness checks, backtest, site JSON, icons
make test           # unit tests
make dev            # http://localhost:3102

make redpanda-up    # single-node Redpanda (docker-compose.yml)
make kafka-check    # replay the Samus Swan window through Redpanda and compare
make live           # aisstream.io consumer, needs AISSTREAM_API_KEY in .env
make live-check     # listen for 10 minutes and run the rows through the processor
```

## Limits

- One testable incident is a case study, not an accuracy figure.
- Danish receivers do not reach the Gulf of Finland, where several of the recent breaks happened, and the public daily files stop in February 2025.
- EMODnet's Baltic coverage is mostly German and Norwegian data, so many Danish and Swedish routes are missing. `make osm` can add every OpenStreetMap subsea cable in the area through the Overpass API (resumable; the public servers were overloaded when I built this, so the published numbers use EMODnet plus the pinned Bornholm route only).
- Public cable routes are approximate. A route that is a kilometre off can move a ship in or out of range, and a cable that is missing from both EMODnet and OpenStreetMap is invisible to the rules.
- The free aisstream.io feed carries about a thirteenth of the archive's report rate, too sparse for the behavior rules in live use.
- A ship with its transponder switched off disappears from any system built on AIS.
- A flag means behavior consistent with anchor drag near a cable. It is a lead for a person to check, never a finding of fault.

## Data and licences

- AIS: Danish Maritime Authority historical AIS data (aisdata.ais.dk).
- Cable routes: EMODnet Human Activities, CC BY 4.0, data originator Cogea Srl; OpenStreetMap contributors, ODbL 1.0.
- Land: Natural Earth, via the `world-atlas` package.
- Incidents: public reporting and investigators' statements, cited row by row in `data/reference/incidents.csv`.

## Author

Built by Omer Faizan. More of my work is at [omerfaizan.com](https://omerfaizan.com/).
