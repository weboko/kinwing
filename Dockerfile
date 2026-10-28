# kinwing — the reader service and the kw CLI, without any agent or credential.
# Agents (Claude Code, Codex) stay in ai-box; this image only reads and writes the
# knowledge home mounted at /knowledge.
# Same base and Python (3.12, no PyYAML) as the ai-box images, so kw behaves identically here
# and inside the agent containers.
FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
# pdftotext for PDF sources, git for the kb history; jq, patch and procps only so the test
# suite can drive agent-orchestrator here. kw itself is stdlib-only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 poppler-utils git ca-certificates patch jq procps \
    && rm -rf /var/lib/apt/lists/*

COPY skills /opt/kinwing/skills
COPY tests /opt/kinwing/tests
COPY integrations /opt/kinwing/integrations
RUN ln -s /opt/kinwing/skills/knowledge-research/bin/kw /usr/local/bin/kw

ENV KW_HOME=/knowledge \
    KW_READER_HOST=0.0.0.0 \
    KW_READER_PORT=8765 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/kinwing
VOLUME ["/knowledge"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/home', timeout=4)" || exit 1

# Inside the container the reader listens on all interfaces; compose publishes it on the
# host's 127.0.0.1 only. Set KW_READER_TOKEN to require a token as well.
ENTRYPOINT ["kw"]
CMD ["serve"]
