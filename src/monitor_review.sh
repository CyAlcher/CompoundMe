#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SCRIPT_DIR/../config/app_config.json"
CONDA_ROOT="${COMPOUNDME_CONDA_ROOT:-$HOME/miniconda3}"
CONDA_ENV="${COMPOUNDME_CONDA_ENV:-agent}"
TARGET_DATE="${AI_REVIEW_TARGET_DATE:-$(date -v-1d +%F)}"

cd "$SCRIPT_DIR"
source "$CONDA_ROOT/etc/profile.d/conda.sh"
conda activate "$CONDA_ENV"
python monitor_review.py --config "$CONFIG" --date "$TARGET_DATE"
