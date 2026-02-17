# ============================================================
# Stage 1: Build the picoclaw binary
# ============================================================
FROM golang:1.25.7-alpine AS builder

RUN apk add --no-cache git make

WORKDIR /src

ARG PICOCLAW_VERSION=v0.1.1

RUN git clone --depth 1 --branch ${PICOCLAW_VERSION} https://github.com/sipeed/picoclaw.git .
RUN go mod download
RUN make build

# ============================================================
# Stage 2: Runtime image with python and common utilities
# ============================================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install common system tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl wget ca-certificates git zip unzip tar jq imagemagick pandoc poppler-utils nano && \
    apt-get clean && \ 
    rm -rf /var/lib/apt/lists/*

# Install common Python libraries
RUN uv pip install --system --no-cache pandas numpy openpyxl matplotlib seaborn requests beautifulsoup4 yt-dlp openai anthropic tiktoken python-docx pypdf

# Copy picoclaw binary from builder
COPY --from=builder /src/build/picoclaw /usr/local/bin/picoclaw

ARG APP_HOME=/app
ARG PICOCLAW_USER=picoclaw
ARG PICOCLAW_UID=1000
ARG PICOCLAW_HOME=/data
ENV HOME=${PICOCLAW_HOME}

# Create non-root user and directories
RUN set -eux; \
    groupadd -g ${PICOCLAW_UID} ${PICOCLAW_USER}; \
    useradd -m -u ${PICOCLAW_UID} -g ${PICOCLAW_USER} \
            -d ${PICOCLAW_HOME} -s /bin/bash ${PICOCLAW_USER}; \
    mkdir -p ${APP_HOME}; \
    chown -R ${PICOCLAW_UID}:${PICOCLAW_UID} ${APP_HOME} ${PICOCLAW_HOME}

# Install app dependencies
COPY --chown=${PICOCLAW_UID}:${PICOCLAW_UID} requirements.txt ${APP_HOME}/requirements.txt
RUN uv pip install --system --no-cache -r ${APP_HOME}/requirements.txt

# Copy application files
COPY --chown=${PICOCLAW_UID}:${PICOCLAW_UID} server.py start.sh ${APP_HOME}/
COPY --chown=${PICOCLAW_UID}:${PICOCLAW_UID} templates/ ${APP_HOME}/templates/
RUN chmod +x ${APP_HOME}/start.sh

WORKDIR ${APP_HOME}
USER ${PICOCLAW_USER}
ENV PICOCLAW_AGENTS_DEFAULTS_WORKSPACE=${PICOCLAW_HOME}/.picoclaw/workspace

CMD ["/app/start.sh"]
