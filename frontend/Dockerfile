# syntax=docker/dockerfile:1

# ---- build stage: Node compiles the React app into static files -------------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# The commit being built (set by CI), shown in the page footer.
ARG GIT_SHA=dev
ENV VITE_BUILD_SHA=$GIT_SHA
RUN npm run build

# ---- runtime stage: unprivileged Nginx serves the files, no Node at all -----
FROM nginxinc/nginx-unprivileged:1.29-alpine
LABEL org.opencontainers.image.title="bloodlink-frontend" \
      org.opencontainers.image.description="BloodLink React frontend served by Nginx" \
      org.opencontainers.image.source="https://github.com/Ishan007-bot/Bloodlink"

# Pull in Alpine security fixes that landed after the base image was published.
USER root
RUN apk upgrade --no-cache
USER 101

# The Nginx entrypoint renders /etc/nginx/templates/*.template with envsubst at start-up,
# so the backend address is configuration, not baked into the image.
ENV BACKEND_URL=http://backend:8000
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
