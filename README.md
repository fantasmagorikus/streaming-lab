• Project Description
  Streaming Lab is a containerised RTMP-to-HLS playground that showcases dual-origin streaming, an auto-
  failover FastAPI switcher, and a plug-in Prometheus/Grafana monitoring stack—perfect for demonstrating
  hands-on video delivery resilience in a portfolio.

  Highlights

  - Designing end-to-end live streaming pipelines (RTMP ingest, HLS packaging, dual origins)
  - Implementing resilient traffic control logic with FastAPI, async tasks, and Prometheus metrics
  - Orchestrating multi-service environments using Docker Compose, shared volumes, and service networking
  - Instrumenting workloads for observability with Prometheus scrape configs and Grafana dashboards
  - Automating failover/throttling strategies based on media telemetry (segment age heuristics, health probes)

  Stack

  - MediaMTX (RTMP ingest)
  - FFmpeg (HLS packaging, synthetic publisher)
  - Nginx (dual HLS origins)
  - FastAPI + HTTPX + Prometheus client (switcher service)
  - Docker Compose (orchestration and shared volumes)
  - Prometheus (metrics collection)
  - Grafana (dashboards and visualisation)
