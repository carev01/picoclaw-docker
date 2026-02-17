# PicoClaw Helm Chart

[![Build and Push](https://github.com/carev01/picoclaw-helm/actions/workflows/build_and_push.yml/badge.svg)](https://github.com/carev01/picoclaw-helm/actions/workflows/build_and_push.yml)
[![Helm Chart](https://github.com/carev01/picoclaw-helm/actions/workflows/update_helm_chart.yml/badge.svg)](https://github.com/carev01/picoclaw-helm/actions/workflows/update_helm_chart.yml)
[![GitHub release](https://img.shields.io/github/v/release/carev01/picoclaw-helm?include_prereleases)](https://github.com/carev01/picoclaw-helm/releases)
[![Docker](https://img.shields.io/badge/ghcr.io-carev01%2Fpicoclaw--helm%2Fpicoclaw-blue)](https://github.com/carev01/picoclaw-helm/pkgs/container/picoclaw-helm%2Fpicoclaw)

A Helm chart for deploying [PicoClaw](https://github.com/sipeed/picoclaw) on Kubernetes.

PicoClaw is an ultra-lightweight personal AI assistant written in Go, designed to run on low-cost hardware with **<10MB RAM** and **~1s boot time**. This Helm chart deploys PicoClaw with a web-based management interface for easy configuration and monitoring.

## Table of Contents

- [Overview](#overview)
- [Docker Images](#docker-images)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Example Values File](#example-values-file)
- [Usage](#usage)
- [Architecture](#architecture)
- [Upgrading](#upgrading)
- [Uninstallation](#uninstallation)
- [Automation](#automation)
- [Related Projects](#related-projects)
- [Contributing](#contributing)
- [License](#license)

## Overview

This chart packages PicoClaw for Kubernetes deployment, providing:

- **Web Management UI** - Browser-based dashboard for configuration and monitoring
- **Basic Auth Protection** - Secure access with configurable credentials
- **Persistent Storage** - Preserves configuration and workspace across restarts
- **Health Probes** - Kubernetes-native liveness and readiness checks
- **Ingress Support** - Easy external access configuration

## Docker Images

Images are available at GitHub Container Registry:

```bash
ghcr.io/carev01/picoclaw-helm/picoclaw:v0.1.1
ghcr.io/carev01/picoclaw-helm/picoclaw:latest
```

### Supported Platforms

- `linux/amd64`
- `linux/arm64`

## Prerequisites

- Kubernetes 1.19+
- Helm 3.2.0+
- PersistentVolume provisioner (if persistence is enabled)

## Installation

### From GitHub Pages

```bash
helm repo add picoclaw https://carev01.github.io/picoclaw-helm
helm install my-picoclaw picoclaw/picoclaw
```

### From Source

```bash
git clone https://github.com/carev01/picoclaw-helm.git
cd picoclaw-helm
helm install my-picoclaw ./charts/picoclaw
```

### With Custom Values

```bash
helm install my-picoclaw picoclaw/picoclaw -f my-values.yaml
```

## Configuration

### Basic Configuration

The following table lists the configurable parameters of the PicoClaw chart and their default values.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicaCount` | Number of replicas | `1` |
| `image.repository` | Image repository | `ghcr.io/carev01/picoclaw-helm/picoclaw` |
| `image.tag` | Image tag | `v0.1.1` |
| `image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `service.type` | Service type | `ClusterIP` |
| `service.port` | Service port | `8080` |

### Authentication

| Parameter | Description | Default |
|-----------|-------------|---------|
| `auth.adminUsername` | Username for Basic Auth | `admin` |
| `auth.adminPassword` | Password for Basic Auth (auto-generated if empty) | `""` |
| `existingSecret` | Use an existing secret for credentials | `""` |

> **Note**: If `auth.adminPassword` is not set, a random password will be generated during deployment. Check the deployment logs to retrieve the generated password.

### Persistence

| Parameter | Description | Default |
|-----------|-------------|---------|
| `persistence.enabled` | Enable persistent storage | `true` |
| `persistence.storageClass` | Storage class name | `""` (default) |
| `persistence.accessMode` | Access mode | `ReadWriteOnce` |
| `persistence.size` | Size of persistent volume | `2Gi` |

### Ingress

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class name | `""` |
| `ingress.annotations` | Ingress annotations | `{}` |
| `ingress.hosts` | Ingress hosts configuration | See values.yaml |
| `ingress.tls` | TLS configuration | `[]` |

### Resource Limits

| Parameter | Description | Default |
|-----------|-------------|---------|
| `resources.limits.cpu` | CPU limit | `500m` |
| `resources.limits.memory` | Memory limit | `256Mi` |
| `resources.requests.cpu` | CPU request | `100m` |
| `resources.requests.memory` | Memory request | `64Mi` |

### Health Probes

| Parameter | Description | Default |
|-----------|-------------|---------|
| `livenessProbe.enabled` | Enable liveness probe | `true` |
| `readinessProbe.enabled` | Enable readiness probe | `true` |

## Example Values File

```yaml
# Minimal configuration with custom credentials
auth:
  adminUsername: "myadmin"
  adminPassword: "mysecurepassword"

# Enable ingress with TLS
ingress:
  enabled: true
  className: "nginx"
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: picoclaw.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: picoclaw-tls
      hosts:
        - picoclaw.example.com

# Resource configuration
resources:
  limits:
    cpu: 500m
    memory: 256Mi
  requests:
    cpu: 100m
    memory: 64Mi
```

## Usage

### Accessing the Web UI

After deployment, access the PicoClaw web UI:

1. **Port Forward** (for local access):
   ```bash
   kubectl port-forward svc/my-picoclaw 8080:8080
   ```
   Then open http://localhost:8080 in your browser.

2. **Via Ingress** (if enabled):
   Navigate to your configured host URL.

### Configuration Management

The new version of PicoClaw features a web-based configuration system:

- **Dashboard**: View gateway status, provider configuration, and channel status
- **Settings**: Configure providers (OpenAI, Anthropic, Zhipu, etc.) and channels (Telegram, Discord, Slack, etc.)
- **Logs**: Real-time gateway log viewer
- **Gateway Control**: Start, stop, and restart the PicoClaw gateway

All configuration is stored in the persistent volume at `/data/.picoclaw/config.json`.

### Configuring LLM Providers

Through the web UI, you can configure multiple LLM providers:

- **Anthropic** - Claude models
- **OpenAI** - GPT models
- **OpenRouter** - Multi-model gateway
- **Zhipu** - GLM models (default)
- **Gemini** - Google's models
- **Groq** - Fast inference
- **DeepSeek** - DeepSeek models
- **Moonshot** - Moonshot models
- **VLLM** - Self-hosted models
- **NVIDIA** - NVIDIA NIM models

### Channel Configuration

Enable various messaging channels for your AI assistant:

| Channel | Description | Required Config |
|---------|-------------|-----------------|
| Telegram | Telegram bot integration | Bot Token |
| Discord | Discord bot integration | Bot Token |
| Slack | Slack app integration | Bot Token, App Token |
| LINE | LINE messaging | Channel Secret, Channel Access Token |
| Feishu | Feishu/Lark integration | App ID, App Secret |
| DingTalk | DingTalk bot | Client ID, Client Secret |
| QQ | QQ bot | App ID, App Secret |
| WhatsApp | WhatsApp via bridge | Bridge URL |

### Web Search Tools

Configure web search capabilities:

- **DuckDuckGo** - Free search (enabled by default)
- **Brave Search** - API-based search with higher rate limits

## Architecture

The deployment consists of:

1. **Web Server** (Starlette-based) - Management UI and API endpoints
2. **PicoClaw Gateway** - The core AI assistant process
3. **Persistent Volume** - Stores configuration and workspace

```
┌─────────────────────────────────────────┐
│              Pod                        │
│  ┌─────────────────────────────────┐   │
│  │      Web Server (Port 8080)     │   │
│  │   - Dashboard UI                │   │
│  │   - Configuration API           │   │
│  │   - Basic Auth                  │   │
│  └──────────────┬──────────────────┘   │
│                 │ Manages               │
│                 ▼                       │
│  ┌─────────────────────────────────┐   │
│  │    PicoClaw Gateway Process     │   │
│  │    (Controlled by Web Server)   │   │
│  └─────────────────────────────────┘   │
│                 │                       │
│                 ▼                       │
│  ┌─────────────────────────────────┐   │
│  │    Persistent Volume            │   │
│  │    /data/.picoclaw/             │   │
│  │    - config.json                │   │
│  │    - workspace/                 │   │
│  │    - sessions/                  │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

## Upgrading

```bash
helm upgrade my-picoclaw picoclaw/picoclaw
```

## Uninstallation

```bash
helm uninstall my-picoclaw
```

> **Note**: This will remove the deployment but preserve the PVC. To delete the PVC as well:
> ```bash
> kubectl delete pvc -l app.kubernetes.io/instance=my-picoclaw
> ```

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

## Related Projects

- [PicoClaw](https://github.com/sipeed/picoclaw) - The upstream PicoClaw project
- [PicoClaw Railway Template](https://github.com/arjunkomath/picoclaw-railway-template) - 1-click deploy template for Railway

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
│       ├── Chart.yaml              # Helm chart definition
│       ├── values.yaml             # Helm chart default values and config reference
│       └── templates/              # Helm chart templates for the required Kubernetes artifacts
│           ├── deployment.yaml
│           ├── ingress.yaml
│           ├── pvc.yaml
│           ├── secret.yaml
│           ├── service.yaml
│           ├── serviceaccount.yaml
│           └── _helpers.tpl
├── templates/
│   └── index.html        # Template for the web management console interface
├── .last-build-version   # Last upstream PicoClaw version built

├── Dockerfile        # Builds PicoClaw on top of a python-trixie image with common system utilities and python libraries for better AI agent autonomy
├── requirements.txt  # Requirements for the Python-based web management console
├── server.py         # Web management console based on Starlette with basic authentication built-in
├── start.sh          # Container start script
└── README.md
```

## License

This project is provided as-is for building and deploying PicoClaw. PicoClaw itself is licensed under its own terms - see [upstream repository](https://github.com/sipeed/picoclaw) for details.
This project is licensed under UNLICENSE - see the [LICENSE](LICENSE) file for details.

## Links

- [PicoClaw (Upstream)](https://github.com/sipeed/picoclaw)
- [Docker Images](https://github.com/carev01/picoclaw-helm/pkgs/container/picoclaw-docker%2Fpicoclaw)
- [Helm Chart Releases](https://github.com/carev01/picoclaw-helm/releases)
- [Issues](https://github.com/carev01/picoclaw-helm/issues)
