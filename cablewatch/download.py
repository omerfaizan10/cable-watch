"""Resumable download of one DMA archive file to disk.

Streaming and parsing at the same time stalls the connection whenever parsing falls
behind, and the DMA server resets stalled connections. Downloading first (resuming with
HTTP Range after a reset) and parsing the local file afterwards avoids that.

Usage: python -m cablewatch.download 2024-03-01 data/raw/aisdk-2024-03-01.zip
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

from .dma_archive import UA, url_for


def download(period: str, dest: Path, attempts: int = 20) -> Path:
    url = url_for(period)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".partial")
    with httpx.Client(headers=UA, timeout=httpx.Timeout(60, connect=20), follow_redirects=True) as c:
        total = int(c.head(url).headers["content-length"])
        for attempt in range(attempts):
            have = part.stat().st_size if part.exists() else 0
            if have >= total:
                break
            try:
                with c.stream("GET", url, headers={"Range": f"bytes={have}-"}) as r:
                    if r.status_code not in (200, 206):
                        raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
                    mode = "ab" if r.status_code == 206 else "wb"
                    with open(part, mode) as fh:
                        for chunk in r.iter_bytes(1 << 20):
                            fh.write(chunk)
            except httpx.HTTPError as e:
                print(f"{period}: {type(e).__name__} at {have / 1e6:.0f} MB, resuming", file=sys.stderr)
                time.sleep(min(60, 5 * (attempt + 1)))
        if part.stat().st_size != total:
            raise RuntimeError(f"{period}: got {part.stat().st_size} of {total} bytes")
    part.replace(dest)
    return dest


if __name__ == "__main__":
    t = time.monotonic()
    p = download(sys.argv[1], Path(sys.argv[2]))
    print(f"{sys.argv[1]}: {p.stat().st_size / 1e6:.0f} MB in {time.monotonic() - t:.0f} s")
