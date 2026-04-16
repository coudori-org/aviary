{{- define "aviary-environment.name" -}}
{{ .Values.name | default "default" }}
{{- end -}}

{{- define "aviary-environment.fullname" -}}
aviary-env-{{ include "aviary-environment.name" . }}
{{- end -}}

{{- define "aviary-environment.labels" -}}
aviary/role: agent-runtime
aviary/environment: {{ include "aviary-environment.name" . }}
{{- end -}}

{{- define "aviary-environment.selectorLabels" -}}
aviary/role: agent-runtime
aviary/environment: {{ include "aviary-environment.name" . }}
{{- end -}}
