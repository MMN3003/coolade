# EcoCode Gateway frontend — multi-stage build.
# Stage 1: build the Vite/React/TS SPA with Node 20 (host dev machine may only
# have Node 18; the build itself always happens inside this image, per TECH.md
# §1: "بیلد داخل Docker (Node 18 host بی‌اهمیت)").
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# Stage 2: serve the static dist/ output with a minimal nginx.
# The infra/backend developer (Dev1) owns the root nginx/ reverse-proxy setup
# (TLS, /api and /v1 routing per TECH.md §2); this image is a self-contained,
# standalone way to serve the built SPA on port 80 and can be used directly as
# the `nginx` service's build context, or Dev1 can instead COPY --from=build
# /app/dist out of this image into their own nginx config. Either integration
# path works against this Dockerfile without changes here.
FROM nginx:1.27-alpine AS final
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.spa.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
