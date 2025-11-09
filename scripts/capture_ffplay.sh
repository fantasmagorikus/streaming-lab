#!/usr/bin/env bash
set -euo pipefail

# Capture a short sample via ffmpeg/ffplay-compatible pipeline for evidence logs.
# Usage: STREAM_URL=http://localhost:8080/hls/index.m3u8 ./scripts/capture_ffplay.sh docs/ffplay_probe.log

STREAM_URL="${STREAM_URL:-http://localhost:8080/hls/index.m3u8}"
OUT_PATH="${1:-docs/ffplay_probe_$(date -u +%Y%m%dT%H%M%SZ).log}"
mkdir -p "$(dirname "${OUT_PATH}")"
TMP_VIDEO="$(mktemp /tmp/streaming-lab-ffplay-XXXXXX.ts)"
cleanup() { rm -f "${TMP_VIDEO}"; }
trap cleanup EXIT

echo "[capture_ffplay] Sampling ${STREAM_URL} for 10 seconds..."
{
  echo "# Capture timestamp (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# Stream URL: ${STREAM_URL}"
  echo "# Command: ffmpeg -y -i \"${STREAM_URL}\" -t 10 -c copy ${TMP_VIDEO}"
} > "${OUT_PATH}"

# Record ffmpeg diagnostic output and basic media metadata.
if ffmpeg -hide_banner -loglevel info -y -i "${STREAM_URL}" -t 10 -c copy "${TMP_VIDEO}" >> "${OUT_PATH}" 2>&1; then
  {
    echo
    echo "# ffprobe summary"
    ffprobe -hide_banner -loglevel error -show_streams -show_format "${TMP_VIDEO}"
  } >> "${OUT_PATH}"
  echo "[capture_ffplay] Evidence stored in ${OUT_PATH}"
else
  echo "[capture_ffplay] Failed to pull stream. See ${OUT_PATH} for logs." >&2
  exit 1
fi
