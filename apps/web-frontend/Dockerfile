# Multi-stage build for the web frontend.
#
# The build stage compiles the React + TypeScript single-page app to static assets with Vite. The
# runtime stage serves those assets with Caddy and contains no Node.js — Node is a build-time tool
# only. The build context is this directory (apps/web-frontend), configured in the compose file.

# --- Build stage: compile the SPA to static assets ---
FROM node:24-alpine AS build
WORKDIR /app

# Install dependencies from the lockfile first for reproducible, cache-friendly builds.
COPY package.json package-lock.json ./
RUN npm ci

# Build the production bundle (type-check then bundle) into /app/dist.
COPY . ./
RUN npm run build

# --- Runtime stage: serve the static bundle via Caddy (no Node at runtime) ---
FROM caddy:2.8-alpine
# Least privilege (CR-WEB-LOW-001): a dedicated non-root user serving on an unprivileged port, with
# ownership of the XDG data/config directories Caddy writes to at startup. The Caddy binary ships
# with cap_net_bind_service set (for binding low ports); it is stripped because the SPA serves on an
# unprivileged port and, with no-new-privileges plus a dropped capability set, exec of a
# file-capability binary would otherwise fail with EPERM.
RUN apk add --no-cache libcap \
	&& setcap -r /usr/bin/caddy \
	&& apk del libcap \
	&& addgroup -g 10001 -S web \
	&& adduser -u 10001 -S -G web web \
	&& mkdir -p /data /config \
	&& chown -R 10001:10001 /data /config
# Internal Caddy config: static file server (unprivileged port) with single-page-app routing fallback.
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /usr/share/caddy
USER 10001:10001
EXPOSE 8080
