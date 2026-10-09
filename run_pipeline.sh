#!/usr/bin/env bash
# Rebuild every data file and the dashboard page from the sources.
set -euo pipefail
cd "$(dirname "$0")"
RAW=data/raw
python3 pipeline/fetch_sources.py --out "$RAW"
python3 pipeline/build_data.py --src "$RAW/mirror" \
  --polygons "$RAW/mirror/geographies/localities_2022.zip" \
  --ses "$RAW/socioeconomic_clusters.json"
python3 pipeline/build_polls.py --src "$RAW/polls-data.js"
python3 pipeline/build_final_polls.py --src pipeline/reference/final_polls_k21_k25.json
python3 pipeline/build_turnout.py
python3 pipeline/build_replay.py
python3 pipeline/build_site.py
