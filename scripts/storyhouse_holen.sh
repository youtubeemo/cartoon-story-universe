#!/usr/bin/env bash
# Holt storyhouse-originals (geprüfte Runway/ElevenLabs-Clients + Budgetwächter) in einer FESTEN Version.
set -euo pipefail
COMMIT=$(python -c "from csu.common import STORYHOUSE_COMMIT; print(STORYHOUSE_COMMIT)")
DIR=vendor/storyhouse-originals
if [ ! -d "$DIR/.git" ]; then
  git clone --quiet https://github.com/youtubeemo/storyhouse-originals "$DIR"
fi
git -C "$DIR" fetch --quiet --depth 1 origin "$COMMIT" || true
git -C "$DIR" checkout --quiet "$COMMIT"
echo "storyhouse @ $COMMIT"
