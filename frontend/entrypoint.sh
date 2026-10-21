#!/bin/sh
# Writes the API base URL into a tiny static file at container start, so the
# same built image can point at a different API URL in every environment
# (local compose, Render, Railway) without rebuilding. Vite bakes
# import.meta.env.* into the bundle at `vite build` time, which is too early
# to know a platform-assigned URL -- this runtime file is what api.ts reads
# instead.
set -e
: "${API_BASE_URL:=http://127.0.0.1:8010}"
echo "window.__API_BASE_URL__ = \"${API_BASE_URL}\";" > /usr/share/nginx/html/env.js
exec nginx -g "daemon off;"
