{{/* Common helpers for the aviary-platform chart. */}}

{{- define "aviary-platform.agentsNamespace" -}}
{{ .Values.agentsNamespace | default "agents" }}
{{- end -}}

{{- define "aviary-platform.platformNamespace" -}}
{{ .Values.platformNamespace | default "platform" }}
{{- end -}}
