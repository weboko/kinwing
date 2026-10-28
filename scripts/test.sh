#!/usr/bin/env bash
# Run kinwing's tests.
#
#   scripts/test.sh             unit + scenario tests on this machine (python3 ≥ 3.10), twice:
#                               with PyYAML if installed and with the built-in YAML parser
#   scripts/test.sh --docker    the same inside the kinwing image, then the ai-box integration
#                               test (builds images; needs Docker)
#
# AIBOX_DIR=<weboko/ai-box checkout> enables the agent-orchestrator and ai-box tests. Without it
# the script clones ai-box into .no-aibox/… once (needs network), or skips those tests.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -z "${AIBOX_DIR:-}" ]]; then
  if [[ ! -d .cache/ai-box ]]; then
    git clone -q --depth 1 https://github.com/weboko/ai-box.git .cache/ai-box 2>/dev/null || true
  fi
  [[ -d .cache/ai-box ]] && export AIBOX_DIR="$PWD/.cache/ai-box"
fi

if [[ "${1:-}" == "--docker" ]]; then
  docker build -q --network host -t kinwing:latest . >/dev/null
  docker run --rm -e KW_YAML=builtin ${AIBOX_DIR:+-e AIBOX_DIR=/aibox -v "$AIBOX_DIR:/aibox:ro"} \
    --entrypoint python3 kinwing:latest -m unittest discover -s tests -t .
  KW_TEST_DOCKER=1 python3 -m unittest tests.test_aibox_integration -v
  exit 0
fi

python3 -m unittest discover -s tests -t . "$@"
KW_YAML=builtin python3 -m unittest discover -s tests -t . "$@"
