{{/*
Expand the name of the chart.
*/}}
{{- define "picoclaw.name" -}}
{{- .Chart.Name | default "picoclaw" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "picoclaw.fullname" -}}
{{- $name := include "picoclaw.name" . -}}
{{- if and .Values.fullnameOverride (not (empty .Values.fullnameOverride)) -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else if and .Release.Name (not (empty .Release.Name)) -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- else -}}
{{- $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "picoclaw.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "picoclaw.labels" -}}
helm.sh/chart: {{ include "picoclaw.chart" . }}
{{ include "picoclaw.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service | default "Helm" }}
{{- end -}}

{{/*
Selector labels
*/}}
{{- define "picoclaw.selectorLabels" -}}
app.kubernetes.io/name: {{ include "picoclaw.name" . }}
app.kubernetes.io/instance: {{ .Release.Name | default "release" }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "picoclaw.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "picoclaw.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}
