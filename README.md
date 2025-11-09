# Streaming Lab — Resilient RTMP → HLS Pipeline with Automatic Failover

[![Docs (EN)](https://img.shields.io/badge/docs-EN-blue)](README.md)
[![Docs (pt‑BR)](https://img.shields.io/badge/docs-pt%E2%80%91BR-blue)](README.pt-BR.md)

English-first documentation for a containerised live-stream lab that ingests RTMP with MediaMTX, packages two independent HLS origins, orchestrates failover via a FastAPI switcher, and exports Prometheus metrics ready for Grafana dashboards.

> 🇧🇷 Leia este conteúdo em português: [README.pt-BR.md](README.pt-BR.md)

## Contents
- [What I Built & Why](#what-i-built--why)
- [Architecture & Flow](#architecture--flow)
- [Components & Versions](#components--versions)
- [Runbook (Setup → Failover Drills → Teardown)](#runbook-setup--failover-drills--teardown)
- [Monitoring Stack (Prometheus + Grafana)](#monitoring-stack-prometheus--grafana)
- [Switcher Logic & Metrics](#switcher-logic--metrics)
- [Evidence & Dashboards](#evidence--dashboards)
- [Troubleshooting](#troubleshooting)
- [Project Layout](#project-layout)
- [Backlog / Next Steps](#backlog--next-steps)
- [Changelog, Contributing, License](#changelog-contributing-license)

## What I Built & Why
- **Live video resilience lab**: Demonstrates a full RTMP → HLS workflow with dual origins so portfolio reviewers can watch active failovers instead of static diagrams.
- **Automatic traffic control**: Custom FastAPI switcher decides which origin to serve by watching playlist freshness (segment age heuristics) and HTTP health.
- **Observability baked in**: Prometheus scrapes the switcher metrics and Grafana dashboard screenshots show signal quality for interviews.
- **Portfolio ready**: All assets (configs, compose files, docs, evidence PNGs) live under version control to mirror the style of the pentest/defensive labs in this homelab.

## Architecture & Flow
```
┌──────────────┐    RTMP     ┌──────────────┐    HLS    ┌───────────────┐
│ ffmpeg input │────────────▶│ MediaMTX     │──────────▶│ Packagers     │
└──────┬───────┘             └──────┬───────┘           └──────┬────────┘
       │        push test pattern          │write segments      │serve playlists
       │                                    ▼                   ▼
┌──────▼───────┐  HLS segments   ┌──────────▼────────┐   HTTP   ┌──────────────┐
│ publisher    │────────────────▶│ origin-primary    │─────────▶│ switcher     │
│ (daemon)     │                 └──────────┬────────┘          │ FastAPI +   │
│ / profile    │────────────────▶┌──────────▼────────┐          │ Prometheus  │
└──────────────┘  HLS segments   │ origin-backup     │◀────────▶│ metrics     │
                                 └──────────┬────────┘          └──────┬──────┘
                                            │                          │ scrape / dashboards
                                            ▼                          ▼
                                         Prometheus ─────────────▶ Grafana
```
- MediaMTX receives RTMP and distributes it to two FFmpeg packagers that write HLS playlists/segments into dedicated volumes.
- Two Nginx origins host the HLS content on `http://localhost:8081` (primary) and `http://localhost:8082` (backup).
- The FastAPI switcher proxies `/hls/*` traffic from `http://localhost:8080/hls/index.m3u8`, automatically swapping origins when segment age exceeds the threshold.
- Prometheus and Grafana (optional overlay) run on the same Docker network (`streaming-lab_default`) for zero-config scraping.

## Components & Versions
- **Ingest**: `bluenviron/mediamtx:latest` (RTMP on `1936:1935` mapped through to host).
- **Publisher(s)**: `jrottenberg/ffmpeg:6.1-alpine` (automatic `publisher-daemon` + manual `ffmpeg-pub` profile).
- **Packagers**: two FFmpeg containers writing HLS with 2s segments and `#EXT-X-PROGRAM-DATE-TIME`.
- **Origins**: `nginx:alpine` serving `/usr/share/nginx/html/hls` per origin.
- **Switcher**: custom FastAPI app (Uvicorn) under `switcher/`, exporting Prometheus metrics on port `8080`.
- **Observability**: `prom/prometheus:latest` + `grafana/grafana:latest` wired through `monitoring/docker-compose.yml`.
- **Configs**: `configs/nginx-origin.conf` (cache headers, HLS route) and `monitoring/prometheus.yml` (scrape config).

## Runbook (Setup → Failover Drills → Teardown)
Prereqs: Docker, Docker Compose, and access to this repository at `homelab-security/github-sync/streaming-lab`.

```bash
cd homelab-security/github-sync/streaming-lab

# 1) Launch ingest, packagers, origins, switcher, and the autoplay publisher
docker compose up -d

# 2) (Optional) Start the manual publisher profile for additional RTMP load
docker compose --profile manual up ffmpeg-pub -d

# 3) Watch the stream via the switcher endpoint (HLS player or ffplay)
ffplay http://localhost:8080/hls/index.m3u8

# 4) Simulate failover by stopping the primary origin/packager
docker compose stop origin-primary
# or: docker compose stop packager-primary

# 5) Observe the switcher metrics / Grafana dashboard

# 6) Bring the system back to normal
docker compose start origin-primary packager-primary

# 7) Tear everything down when finished
docker compose down -v
```

Tips:
- Use `docker compose logs -f switcher` to watch which origin is active.
- The RTMP ingest is mapped to `rtmp://localhost:1936/mystream` so OBS or another publisher can replace the synthetic FFmpeg source.
- All HLS content lives inside named volumes (`hls_primary`, `hls_backup`); `docker volume rm` cleans them fully.

## Monitoring Stack (Prometheus + Grafana)
The monitoring folder ships an optional overlay that attaches to the main Docker network.

```bash
# With the base stack already running:
cd homelab-security/github-sync/streaming-lab/monitoring
docker compose up -d   # Prometheus on :9090, Grafana on :3000
```

- Grafana auto-loads the Prometheus datasource + dashboard via `monitoring/grafana/provisioning/**`.
- The JSON dashboard (`monitoring/grafana/dashboards/streaming-lab.json`) mirrors the panels shown in `docs/print_03_grafana_dashboard.png`.
- Sample PromQL snippets:
  - `segment_age_seconds{origin="primary"}` — freshness of the playlist MediaMTX feeds into the switcher.
  - `switcher_active_origin` — `1` when serving the primary origin, `0` when the backup takes over.
  - `rate(failovers_total[5m])` — alert if failovers exceed an acceptable rate.

### Grafana alerts
- Two Unified Alerting rules ship by default (`Segment Age High (Primary)` and `Failover Burst (>=2 in 5m)`), provisioned from `monitoring/grafana/provisioning/alerting/alerts.yml`.
- Contact points/notification policies are not committed—configure them in Grafana (`Alerting › Contact points`) after the stack is up.
- Tweak thresholds or add new alerts by editing the YAML and re-running `docker compose up -d` in `monitoring/`.

## Switcher Logic & Metrics
- Environment variables (override by editing `docker-compose.yml`):
  - `PRIMARY_BASE_URL` / `BACKUP_BASE_URL`: HLS base URLs (default `http://origin-primary/hls` and `http://origin-backup/hls`).
  - `PLAYLIST_PATH`: relative path (`index.m3u8`).
  - `CHECK_INTERVAL_SECONDS`: cadence for probing both playlists (default `5` seconds).
  - `SEGMENT_AGE_THRESHOLD_SECONDS`: maximum allowed staleness per playlist (default `20` seconds).
  - `REQUIRED_WINDOWS`: number of consecutive bad/good probes before flipping (default `3`).
- Metrics exported on `/metrics`:
  - `switcher_active_origin` (`Gauge`): `1` for primary, `0` for backup.
  - `segment_age_seconds{origin}` (`Gauge`): last `#EXT-X-PROGRAM-DATE-TIME` delta for each playlist.
  - `origin_http_5xx_total{origin}` (`Counter`): counts 5xx responses encountered while polling.
  - `failovers_total` / `switchbacks_total`: counters for transitions to backup and back to primary.
- The `/hls/{path}` route proxies requests to whichever origin is active; `/healthz` reports JSON status for external health checks.

## Evidence & Dashboards
Screenshots live under `docs/` for portfolio usage:
- `docs/Overview.png` — lab topology annotated for slide decks.
- `docs/print_01_prometheus_targets.png` — scrape status showing switcher availability.
- `docs/print_02_grafana_datasource_ok.png` — Grafana Prometheus datasource wiring.
- `docs/print_03_grafana_dashboard.png` — dashboard with failover + segment age panels.
- `docs/Pasted image*.png` — raw captures of MediaMTX stats, switcher metrics, and failover drills.

### Capture fresh ffplay evidence
Use the helper script to pull a 10-second HLS sample and store the ffmpeg/ffprobe logs:

```bash
cd homelab-security/github-sync/streaming-lab
bash scripts/capture_ffplay.sh docs/ffplay_probe_$(date -u +%Y%m%dT%H%M%SZ).log
```

Override `STREAM_URL` if the switcher runs elsewhere. The script writes evidence to `docs/ffplay_probe_*.log`.

## Troubleshooting
- **Ports already in use**: `netstat -tulpn | grep 1936` or `lsof -i :8081` to discover conflicting services, then stop them or change host mappings.
- **OBS / ffplay cannot connect to RTMP**: ensure `docker compose ps ingest` is healthy; restart the `ingest` service if MediaMTX crashed.
- **Playlist stale even after recovery**: remove leftover HLS segments (`docker volume rm streaming-lab_hls_primary streaming-lab_hls_backup`) and recreate the stack.
- **Prometheus cannot reach switcher**: confirm both compose projects share the `streaming-lab_default` network (created by the base compose).
- **Grafana empty dashboard**: add the Prometheus datasource manually and set the default time range to the last 15 minutes to catch recent failovers.

## Project Layout
- `docker-compose.yml` — main RTMP → HLS stack (ingest, packagers, origins, switcher, publishers).
- `configs/nginx-origin.conf` — shared Nginx config for both origins (cache headers, CORS, HLS alias).
- `switcher/` — FastAPI application, Dockerfile, and Python requirements.
- `monitoring/` — Prometheus + Grafana overlay (pre-provisioned datasource + dashboards).
- `scripts/` — automation helpers (e.g., `capture_ffplay.sh` for evidence capture).
- `docs/` — annotated diagrams, Prometheus target screenshots, and Grafana dashboards.
- `LICENSE` — MIT license inherited from the upstream repository.

## Backlog / Next Steps
1. Add alerting rules (Prometheus Alertmanager or Grafana Alerting) for `segment_age_seconds` spikes.
2. Harden the stack (read-only FS for Nginx, health probes for packagers, resource limits).
3. Extend switcher logic with weighted round-robin or geo-aware decisions.

## Changelog, Contributing, License
- Track notable updates in commits or add a `CHANGELOG.md` mirroring the pentest lab if the scope grows.
- Contributions: fork/branch, run `docker compose up` locally, then open a PR.
- License: MIT — see `LICENSE`.
