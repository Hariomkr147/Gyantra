# ── Docker image for the Gyantra React frontend ──────────────────────────
# Multi-stage: builds the static bundle, serves it from nginx.

# --- build stage ---
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# VITE_API_URL (if set) is baked in at build time for production.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# --- serve stage ---
FROM nginx:1.27-alpine

# SPA routing: any non-asset path falls through to index.html.
RUN printf '%s\n' \
    'server {' \
    '  listen 80;' \
    '  server_name _;' \
    '  root /usr/share/nginx/html;' \
    '  index index.html;' \
    '  location /api/ {' \
    '    proxy_pass http://backend:8000;' \
    '    proxy_http_version 1.1;' \
    '    proxy_set_header Host $host;' \
    '    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;' \
    '    proxy_buffering off;' \
    '    proxy_read_timeout 3600s;' \
    '  }' \
    '  location / { try_files $uri $uri/ /index.html; }' \
    '  location = /healthz { access_log off; return 200 "ok"; }' \
    '}' > /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/healthz || exit 1
