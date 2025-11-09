# Streaming Lab — Pipeline RTMP → HLS Resiliente com Failover Automático

Documentação em português para o laboratório de streaming containerizado que ingere RTMP via MediaMTX, empacota duas origens HLS independentes, faz failover automático com FastAPI e exporta métricas Prometheus prontas para dashboards Grafana.

> 🇺🇸 English-first docs: veja [README.md](README.md)

## Sumário
- [O que foi construído e por quê](#o-que-foi-construído-e-por-quê)
- [Arquitetura e fluxo](#arquitetura-e-fluxo)
- [Componentes e versões](#componentes-e-versões)
- [Runbook (Setup → Testes de Failover → Teardown)](#runbook-setup--testes-de-failover--teardown)
- [Stack de monitoramento (Prometheus + Grafana)](#stack-de-monitoramento-prometheus--grafana)
- [Lógica do switcher e métricas](#lógica-do-switcher-e-métricas)
- [Evidências e dashboards](#evidências-e-dashboards)
- [Troubleshooting](#troubleshooting)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Backlog / próximos passos](#backlog--próximos-passos)
- [Changelog, contribuição, licença](#changelog-contribuição-licença)

## O que foi construído e por quê
- **Lab de resiliência de streaming**: demonstra um fluxo completo RTMP → HLS com origens redundantes para mostrar failover em tempo real no portfólio.
- **Controle automático de tráfego**: switcher FastAPI decide qual origem servir monitorando a idade das playlists (heurística de segmentos) e saúde HTTP.
- **Observabilidade nativa**: Prometheus coleta métricas e Grafana exibe painéis para entrevistas/demos.
- **Portfólio alinhado**: mesma abordagem dos labs de pentest/SOC — código, configs, docs e PNGs versionados no repositório.

## Arquitetura e fluxo
```
┌──────────────┐    RTMP     ┌──────────────┐    HLS    ┌───────────────┐
│ ffmpeg input │────────────▶│ MediaMTX     │──────────▶│ Packagers     │
└──────┬───────┘             └──────┬───────┘           └──────┬────────┘
       │        padrão sintético            │escreve segmentos  │serve playlists
       │                                    ▼                   ▼
┌──────▼───────┐  segmentos HLS  ┌──────────▼────────┐   HTTP   ┌──────────────┐
│ publisher    │────────────────▶│ origin-primary    │─────────▶│ switcher     │
│ (daemon/perf)│                 └──────────┬────────┘          │ FastAPI +   │
└──────────────┘  segmentos HLS  ┌──────────▼────────┐          │ Prometheus  │
                                 │ origin-backup     │◀────────▶│ metrics     │
                                 └──────────┬────────┘          └──────┬──────┘
                                            │                          │ métricas/dashboards
                                            ▼                          ▼
                                         Prometheus ─────────────▶ Grafana
```
- MediaMTX recebe RTMP e distribui para dois FFmpegs que escrevem playlists HLS em volumes dedicados.
- Duas origens Nginx expõem `http://localhost:8081/hls/index.m3u8` (primária) e `http://localhost:8082/hls/index.m3u8` (backup).
- O switcher FastAPI publica `http://localhost:8080/hls/index.m3u8`, trocando de origem quando a idade dos segmentos passa do limiar.
- Prometheus/Grafana rodam em `monitoring/` compartilhando a rede Docker `streaming-lab_default`.

## Componentes e versões
- **Ingest**: `bluenviron/mediamtx:latest` (porta host `1936` → container `1935`).
- **Publishers**: `jrottenberg/ffmpeg:6.1-alpine` (daemon automático + perfil manual `ffmpeg-pub`).
- **Packagers**: dois containers FFmpeg gerando HLS com segmentos de 2s e `#EXT-X-PROGRAM-DATE-TIME`.
- **Origens**: `nginx:alpine` servindo `/usr/share/nginx/html/hls`.
- **Switcher**: app FastAPI (Uvicorn) em `switcher/`, com métricas Prometheus expostas em `:8080`.
- **Observabilidade**: `prom/prometheus` + `grafana/grafana` via `monitoring/docker-compose.yml`.
- **Configs**: `configs/nginx-origin.conf` e `monitoring/prometheus.yml`.

## Runbook (Setup → Testes de Failover → Teardown)
Pré-requisitos: Docker + Docker Compose, repositório clonado em `homelab-security/github-sync/streaming-lab`.

```bash
cd homelab-security/github-sync/streaming-lab

# 1) Subir ingest, packagers, origens, switcher e publisher automático
docker compose up -d

# 2) (Opcional) Iniciar o publisher manual para gerar carga extra
docker compose --profile manual up ffmpeg-pub -d

# 3) Reproduzir o stream via switcher (HLS player, VLC ou ffplay)
ffplay http://localhost:8080/hls/index.m3u8

# 4) Forçar failover parando a origem/packager primária
docker compose stop origin-primary
# ou: docker compose stop packager-primary

# 5) Observar métricas (Prometheus/Grafana) e logs do switcher

# 6) Restaurar a origem primária
docker compose start origin-primary packager-primary

# 7) Encerrar tudo
docker compose down -v
```

Dicas:
- `docker compose logs -f switcher` mostra qual origem está ativa.
- `rtmp://localhost:1936/mystream` pode receber publicadores externos (OBS, etc.).
- Volumes `hls_primary` e `hls_backup` guardam as playlists; remova-os se precisar limpar resíduos.

## Stack de monitoramento (Prometheus + Grafana)
```bash
cd homelab-security/github-sync/streaming-lab/monitoring
docker compose up -d   # Prometheus :9090, Grafana :3000
```

- Grafana carrega automaticamente o datasource e o dashboard via `monitoring/grafana/provisioning/**`.
- O JSON `monitoring/grafana/dashboards/streaming-lab.json` reflete os painéis exibidos em `docs/print_03_grafana_dashboard.png`.
- Consultas úteis:
  - `segment_age_seconds{origin="primary"}` — idade da playlist.
  - `switcher_active_origin` — 1 primário, 0 backup.
  - `rate(failovers_total[5m])` — alerta de failover frequente.

### Alertas Grafana
- Duas regras de alerta já vêm prontas (`Segment Age High (Primary)` e `Failover Burst (>=2 in 5m)`), provisionadas via `monitoring/grafana/provisioning/alerting/alerts.yml`.
- Configure os canais de notificação no Grafana (`Alerting › Contact points`) após subir a stack; nenhum contato é versionado aqui.
- Ajuste os thresholds (ou crie novos alerts) editando o YAML e executando novamente `docker compose up -d` em `monitoring/`.

## Lógica do switcher e métricas
- Variáveis de ambiente (editar `docker-compose.yml`):
  - `PRIMARY_BASE_URL` / `BACKUP_BASE_URL`: endpoints HLS (padrão `http://origin-primary/hls` e `http://origin-backup/hls`).
  - `PLAYLIST_PATH`: caminho relativo (`index.m3u8`).
  - `CHECK_INTERVAL_SECONDS`: intervalo de checagem (5s).
  - `SEGMENT_AGE_THRESHOLD_SECONDS`: idade máxima aceitável (20s).
  - `REQUIRED_WINDOWS`: janelas consecutivas ruins/boas antes de trocar (3).
- Métricas em `/metrics`:
  - `switcher_active_origin` — gauge binário (primário/backup).
  - `segment_age_seconds{origin}` — diferença entre agora e o último `#EXT-X-PROGRAM-DATE-TIME`.
  - `origin_http_5xx_total{origin}` — erros 5xx detectados nos polls.
  - `failovers_total` / `switchbacks_total` — contadores de transições.
- Endpoints extras: `/hls/{path}` (proxy com failover) e `/healthz` (status JSON).

## Evidências e dashboards
- `docs/Overview.png` — topologia anotada.
- `docs/print_01_prometheus_targets.png` — scrape configurado.
- `docs/print_02_grafana_datasource_ok.png` — datasource Prometheus validado.
- `docs/print_03_grafana_dashboard.png` — dashboard com painel de failover.
- `docs/Pasted image*.png` — capturas cruas de MediaMTX, métricas e drills.

### Capturar evidências com ffplay
Use o helper script para coletar 10 segundos do HLS e registrar os logs do ffmpeg/ffprobe:

```bash
cd homelab-security/github-sync/streaming-lab
bash scripts/capture_ffplay.sh docs/ffplay_probe_$(date -u +%Y%m%dT%H%M%SZ).log
```

Defina `STREAM_URL` se o switcher estiver exposto em outro host/porta. Os logs ficam em `docs/ffplay_probe_*.log`.

## Troubleshooting
- **Portas em uso**: verifique com `lsof -i :1936` ou `lsof -i :8081` e libere o recurso.
- **RTMP indisponível**: confira `docker compose ps ingest`; reinicie o serviço se o MediaMTX travou.
- **Playlist velha**: remova volumes `hls_primary` / `hls_backup` e suba o stack novamente.
- **Prometheus sem acesso ao switcher**: confirme que o network `streaming-lab_default` existe antes de subir o compose de monitoring.
- **Grafana vazio**: defina a fonte de dados corretamente e ajuste o range de tempo para os últimos 15 minutos.

## Estrutura do projeto
- `docker-compose.yml` — stack principal RTMP → HLS.
- `configs/nginx-origin.conf` — configuração compartilhada das origens.
- `switcher/` — app FastAPI, Dockerfile e dependências.
- `monitoring/` — overlay com Prometheus/Grafana (datasource + dashboards provisionados).
- `scripts/` — automações (ex.: `capture_ffplay.sh` para evidências).
- `docs/` — diagramas e screenshots.
- `LICENSE` — licença MIT.

## Backlog / próximos passos
1. Criar alertas para `segment_age_seconds` (Alertmanager ou Grafana Alerting).
2. Endurecer containers (filesystem read-only, healthchecks, limites de recursos).
3. Evoluir o switcher para balanceamento ponderado ou awareness geográfica.

## Changelog, contribuição, licença
- Use commits ou crie `CHANGELOG.md` para rastrear evoluções maiores.
- Contribuições: fork/branch, `docker compose up`, PR.
- Licença MIT — veja `LICENSE`.
