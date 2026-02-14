# PicoClaw Docker

[![Build and Push](https://github.com/carev01/picoclaw-docker/actions/workflows/build_and_push.yml/badge.svg)](https://github.com/carev01/picoclaw-docker/actions/workflows/build_and_push.yml)
[![Helm Chart](https://github.com/carev01/picoclaw-docker/actions/workflows/update_helm_chart.yml/badge.svg)](https://github.com/carev01/picoclaw-docker/actions/workflows/update_helm_chart.yml)
[![GitHub release](https://img.shields.io/github/v/release/carev01/picoclaw-docker?include_prereleases)](https://github.com/carev01/picoclaw-docker/releases)
[![Docker](https://img.shields.io/badge/ghcr.io-carev01%2Fpicoclaw--docker%2Fpicoclaw-blue)](https://github.com/carev01/picoclaw-docker/pkgs/container/picoclaw-docker%2Fpicoclaw)

Automated Docker builds and Kubernetes Helm charts for [PicoClaw](https://github.com/sipeed/picoclaw) - an ultra-lightweight AI assistant powered by Go, running on less than 10MB RAM.

## Table of Contents

- [Overview](#overview)
- [Docker Images](#docker-images)
- [Helm Chart Installation](#helm-chart-installation)
  - [Method 1: GitHub Pages (Recommended)](#method-1-github-pages-recommended)
  - [Method 2: OCI Registry](#method-2-oci-registry)
- [Configuration](#configuration)
  - [Basic Configuration](#basic-configuration)
  - [Channel Configuration](#channel-configuration)
  - [Provider Configuration](#provider-configuration)
  - [Tools Configuration](#tools-configuration)
- [Usage Examples](#usage-examples)
- [Automation](#automation)
- [Upgrading](#upgrading)
- [Contributing](#contributing)

## Overview

This repository provides:

1. **Automated Docker builds** - Automatically builds and publishes Docker images when new PicoClaw releases are published upstream
2. **Helm Charts** - Kubernetes deployment charts for running PicoClaw in gateway mode
3. **Automated Chart Updates** - Helm charts are automatically updated when new images are built

PicoClaw gateway mode runs as a long-running service that connects to chat platforms like Telegram, Discord, QQ, DingTalk, and LINE, making it perfect for Kubernetes deployments.

## Docker Images

Images are available at GitHub Container Registry:

```bash
ghcr.io/carev01/picoclaw-docker/picoclaw:v0.1.1
ghcr.io/carev01/picoclaw-docker/picoclaw:latest
```

### Supported Platforms

- `linux/amd64`
- `linux/arm64`

## Helm Chart Installation

### Method 1: GitHub Pages (Recommended)

No authentication required - works with standard `helm repo add`:

```bash
# Add the Helm repository
helm repo add picoclaw https://carev01.github.io/picoclaw-docker

# Update repository
helm repo update

# Search for available versions
helm search repo picoclaw --versions
```

## Configuration

### Basic Installation

Create a `values.yaml` file with your configuration:

```yaml
# values.yaml - Minimal configuration for Telegram
channels:
  telegram:
    enabled: true
    token: "YOUR_BOT_TOKEN"

providers:
  openrouter:
    apiKey: "YOUR_OPENROUTER_API_KEY"
```

Install the chart:

```bash
helm install picoclaw picoclaw/picoclaw \
  -n picoclaw --create-namespace \
  -f values.yaml
```

### Basic Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicaCount` | Number of replicas | `1` |
| `image.repository` | Image repository | `ghcr.io/carev01/picoclaw-docker/picoclaw` |
| `image.tag` | Image tag | `v0.1.1` |
| `image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `service.type` | Service type | `ClusterIP` |
| `service.port` | Service port | `18790` |
| `persistence.enabled` | Enable persistent storage | `true` |
| `persistence.size` | Storage size | `2Gi` |

### Resource Configuration

PicoClaw is designed to be extremely lightweight:

```yaml
resources:
  limits:
    cpu: 500m
    memory: 128Mi
  requests:
    cpu: 100m
    memory: 32Mi
```

### Channel Configuration

Configure which chat platforms PicoClaw connects to:

#### Telegram

```yaml
channels:
  telegram:
    enabled: true
    token: "YOUR_BOT_TOKEN"
    allowFrom: []  # Empty = allow all users
```

#### Discord

```yaml
channels:
  discord:
    enabled: true
    token: "YOUR_DISCORD_BOT_TOKEN"
    allowFrom: []  # Empty = allow all users/guilds
```

#### QQ (OneBot)

```yaml
channels:
  qq:
    enabled: true
    appId: "YOUR_APP_ID"
    appSecret: "YOUR_APP_SECRET"
    allowFrom: []
```

#### DingTalk

```yaml
channels:
  dingtalk:
    enabled: true
    clientId: "YOUR_CLIENT_ID"
    clientSecret: "YOUR_CLIENT_SECRET"
    allowFrom: []
```

#### LINE

```yaml
channels:
  line:
    enabled: true
    channelSecret: "YOUR_CHANNEL_SECRET"
    channelAccessToken: "YOUR_CHANNEL_ACCESS_TOKEN"
    webhookHost: "0.0.0.0"
    webhookPort: 18791
    webhookPath: "/webhook/line"
    allowFrom: []

# For LINE, you may also want to enable Ingress:
ingress:
  enabled: true
  className: "nginx"
  hosts:
    - host: picoclaw.example.com
      paths:
        - path: /webhook/line
          pathType: Prefix
```

### Provider Configuration

Configure your AI model providers. At least one provider must be configured:

#### OpenRouter (Recommended)

```yaml
providers:
  openrouter:
    apiKey: "sk-or-v1-xxxxx"
    apiBase: ""  # Uses default
```

#### Zhipu AI

```yaml
providers:
  zhipu:
    apiKey: "your-zhipu-api-key"
    apiBase: ""  # Uses default
```

#### Anthropic

```yaml
providers:
  anthropic:
    apiKey: "sk-ant-xxxxx"
    apiBase: ""
```

#### OpenAI

```yaml
providers:
  openai:
    apiKey: "sk-xxxxx"
    apiBase: ""  # Or your custom endpoint
```

#### Google Gemini

```yaml
providers:
  gemini:
    apiKey: "your-gemini-api-key"
    apiBase: ""
```

#### Groq

```yaml
providers:
  groq:
    apiKey: "gsk_xxxxx"
    apiBase: ""
```

### Tools Configuration

Enable web search capabilities:

#### DuckDuckGo (Default, No API Key Required)

```yaml
tools:
  web:
    duckduckgo:
      enabled: true
      maxResults: 5
```

#### Brave Search (Requires API Key)

```yaml
tools:
  web:
    brave:
      enabled: true
      apiKey: "YOUR_BRAVE_API_KEY"
      maxResults: 5
    duckduckgo:
      enabled: false
```

### Advanced Configuration

```yaml
picoclaw:
  gateway:
    host: "0.0.0.0"
    port: 18790
  agents:
    workspace: "/root/.picoclaw/workspace"
    model: "glm-4.7"        # Default model
    maxTokens: 8192          # Maximum response tokens
    temperature: 0.7         # Model temperature
    maxToolIterations: 20    # Max tool call iterations
    restrictToWorkspace: true # Restrict file operations to workspace
  heartbeat:
    enabled: true
    interval: 30

persistence:
  enabled: true
  storageClass: "standard"  # Your storage class
  accessMode: ReadWriteOnce
  size: 2Gi
```

## Usage Examples

### Minimal Telegram Bot

```yaml
# telegram-values.yaml
channels:
  telegram:
    enabled: true
    token: "YOUR_BOT_TOKEN"

providers:
  openrouter:
    apiKey: "YOUR_API_KEY"
```

```bash
helm install picoclaw picoclaw/picoclaw \
  -n picoclaw --create-namespace \
  -f telegram-values.yaml
```

### Multi-Channel Deployment

```yaml
# multi-channel-values.yaml
channels:
  telegram:
    enabled: true
    token: "TELEGRAM_TOKEN"
  discord:
    enabled: true
    token: "DISCORD_TOKEN"

providers:
  openrouter:
    apiKey: "YOUR_API_KEY"

tools:
  web:
    duckduckgo:
      enabled: true
      maxResults: 5

resources:
  limits:
    cpu: 500m
    memory: 128Mi
```

### Using Existing Secrets

For production, use existing secrets instead of putting credentials in values:

```yaml
# Create secret first
existingSecret: "picoclaw-secrets"
```

Create the secret manually:

```bash
kubectl create secret generic picoclaw-secrets \
  -n picoclaw \
  --from-literal=TELEGRAM_BOT_TOKEN="your-token" \
  --from-literal=OPENROUTER_API_KEY="your-key"
```

## Automation

This repository uses several automated workflows:

### 1. Upstream Release Monitor (`check_upstream.yml`)

- Checks for new PicoClaw releases every 24 hours
- Triggers Docker build when new version detected

### 2. Docker Build & Push (`build_and_push.yml`)

- Builds multi-platform Docker images (amd64, arm64)
- Pushes to GitHub Container Registry
- Tags both version and `latest`
- Triggers Helm chart update

### 3. Helm Chart Update (`update_helm_chart.yml`)

- Updates `Chart.yaml` with new appVersion
- Bumps chart patch version
- Packages and publishes chart to OCI registry
- Creates GitHub release

### 4. GitHub Pages Deploy (`helm-pages-deploy.yml`)

- Deploys Helm chart to GitHub Pages
- Updates `index.yaml` for `helm repo add` functionality

### Workflow Summary

```
Upstream Release → check_upstream.yml
                         ↓
              build_and_push.yml (Docker)
                         ↓
              update_helm_chart.yml (Helm)
                         ↓
              helm-pages-deploy.yml (Pages)
```

## Upgrading

### Upgrade to Latest Version

```bash
# Update repository
helm repo update

# Upgrade release
helm upgrade picoclaw picoclaw/picoclaw -n picoclaw
```

### Upgrade with New Values

```bash
helm upgrade picoclaw picoclaw/picoclaw \
  -n picoclaw \
  -f new-values.yaml
```

### Check Current Values

```bash
helm get values picoclaw -n picoclaw
```

## Troubleshooting

### Check Pod Logs

```bash
kubectl logs -n picoclaw -l app.kubernetes.io/name=picoclaw -f
```

### Check Pod Status

```bash
kubectl get pods -n picoclaw
kubectl describe pod -n picoclaw -l app.kubernetes.io/name=picoclaw
```

### Common Issues

1. **Pod not starting**: Check if secrets are correctly configured
2. **Bot not responding**: Verify channel tokens and API keys
3. **Persistence issues**: Check storage class and PVC status

```bash
# Check PVC status
kubectl get pvc -n picoclaw
```

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

### Repository Structure

```
.
├── .github/
│   └── workflows/
│       ├── check_upstream.yml      # Monitor upstream releases
│       ├── build_and_push.yml      # Build Docker images
│       ├── update_helm_chart.yml   # Update Helm chart
│       └── helm-pages-deploy.yml   # Deploy to GitHub Pages
├── charts/
│   └── picoclaw/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│           ├── deployment.yaml
│           ├── service.yaml
│           ├── configmap.yaml
│           ├── secret.yaml
│           ├── pvc.yaml
│           └── _helpers.tpl
└── README.md
```

## License

This project is provided as-is for building and deploying PicoClaw. PicoClaw itself is licensed under its own terms - see [upstream repository](https://github.com/sipeed/picoclaw) for details.

## Links

- [PicoClaw (Upstream)](https://github.com/sipeed/picoclaw)
- [Docker Images](https://github.com/carev01/picoclaw-docker/pkgs/container/picoclaw-docker%2Fpicoclaw)
- [Helm Chart Releases](https://github.com/carev01/picoclaw-docker/releases)
- [Issues](https://github.com/carev01/picoclaw-docker/issues)
