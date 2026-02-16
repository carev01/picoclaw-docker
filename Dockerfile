FROM golang:1.25.7-alpine AS builder

RUN apk add --no-cache git make

WORKDIR /src

ARG PICOCLAW_VERSION=main

RUN git clone --depth 1 --branch ${PICOCLAW_VERSION} https://github.com/sipeed/picoclaw.git .
RUN go mod download
RUN make build

FROM python3.14-trixie-slim

# 1. Install Useful System Tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl wget ca-certificates git zip unzip tar jq imagemagick pandoc poppler-utils build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN uv pip install --system --no-cache pandas numpy openpyxl matplotlib seaborn requests beautifulsoup4 yt-dlp openai anthropic tiktoken python-docx pypdf

COPY --from=builder /src/build/picoclaw /usr/local/bin/picoclaw

COPY requirements.txt /app/requirements.txt
RUN uv pip install --system --no-cache -r /app/requirements.txt

RUN mkdir -p /data/.picoclaw

COPY server.py /app/server.py
COPY templates/ /app/templates/
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

ENV HOME=/data
ENV PICOCLAW_AGENTS_DEFAULTS_WORKSPACE=/data/.picoclaw/workspace

CMD ["/app/start.sh"]
