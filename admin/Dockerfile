# Admin web app for Railway: build the Vite SPA, serve it with nginx.
# Build context: admin/. VITE_* are baked in at build time (Railway passes service variables
# as build args); they are public values, never put secrets here.
FROM node:22-slim AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
ARG VITE_API_BASE_URL
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
RUN pnpm build

# Serve the SPA with nginx. 1.30.7 is the stable release that fixes the November 2026 batch
# (CVE-2026-123007 / CVE-2026-123633 and friends). Those need HTTP/2, which nginx.conf.template
# does not enable, but a fixed, supported branch keeps the bundled OpenSSL/Alpine current too.
FROM nginx:1.30.7-alpine
# The nginx image renders /etc/nginx/templates/*.template with env vars at start (PORT).
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
ENV PORT=8080
EXPOSE 8080
