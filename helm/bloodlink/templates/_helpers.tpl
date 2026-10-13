{{/* Base name for every object: the release name, e.g. "bloodlink". */}}
{{- define "bloodlink.fullname" -}}
{{- .Release.Name | trunc 40 | trimSuffix "-" -}}
{{- end -}}

{{- define "bloodlink.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
app.kubernetes.io/name: bloodlink
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.image.tag | default .Chart.AppVersion | trunc 63 | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: bloodlink
{{- end -}}

{{/* Selector labels for one component: include "bloodlink.selectorLabels" (dict "ctx" . "component" "backend") */}}
{{- define "bloodlink.selectorLabels" -}}
app.kubernetes.io/name: bloodlink
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "bloodlink.image" -}}
{{- if not .ctx.Values.image.tag -}}
{{- fail "image.tag is required: set it to the git commit SHA of the images to deploy" -}}
{{- end -}}
{{- printf "%s/bloodlink-%s:%s" .ctx.Values.image.registry .name .ctx.Values.image.tag -}}
{{- end -}}

{{- define "bloodlink.dbSecretName" -}}
{{- .Values.postgresql.auth.existingSecret | default (printf "%s-db" (include "bloodlink.fullname" .)) -}}
{{- end -}}

{{- define "bloodlink.dbHost" -}}
{{- printf "%s-postgres" (include "bloodlink.fullname" .) -}}
{{- end -}}

{{/* Pod-level security settings that satisfy the "restricted" Pod Security Standard. */}}
{{- define "bloodlink.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: {{ .uid }}
runAsGroup: {{ .uid }}
fsGroup: {{ .uid }}
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "bloodlink.containerSecurityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
{{- end -}}

{{/* Init container that waits until PostgreSQL accepts connections. */}}
{{- define "bloodlink.waitForDb" -}}
- name: wait-for-db
  image: {{ .Values.postgresql.image }}
  imagePullPolicy: {{ .Values.image.pullPolicy }}
  command: ["sh", "-c", "until pg_isready -h {{ include "bloodlink.dbHost" . }} -p 5432 -t 2; do echo waiting for postgres; sleep 2; done"]
  securityContext:
    {{- include "bloodlink.containerSecurityContext" . | nindent 4 }}
    runAsUser: 70
    runAsGroup: 70
  resources:
    requests: {cpu: 10m, memory: 16Mi}
    limits: {cpu: 100m, memory: 64Mi}
{{- end -}}

{{/* DATABASE_URL from the database Secret. */}}
{{- define "bloodlink.databaseEnv" -}}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "bloodlink.dbSecretName" . }}
      key: database-url
{{- end -}}

{{/* Pod template labels: selector labels plus version, without duplicating keys. */}}
{{- define "bloodlink.podLabels" -}}
{{ include "bloodlink.selectorLabels" . }}
app.kubernetes.io/version: {{ .ctx.Values.image.tag | default .ctx.Chart.AppVersion | trunc 63 | quote }}
app.kubernetes.io/part-of: bloodlink
{{- end -}}
