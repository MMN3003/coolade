#!/usr/bin/env bash
# Builds the production images and packs a source-free release bundle:
#   dist/<slug>-<version>/  (+ .tar.gz of that folder)
# Usage: release/build-release.sh [version]     (run from the repo root or release/)
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:-$(date +%Y.%m.%d)-$(git rev-parse --short HEAD)}"
SLUG="${APP_SLUG:-coolade}"   # image name prefix; must match APP_SLUG in the target .env
OUT="dist/${SLUG}-${VERSION}"

echo "==> Building base images (dev compose, local layers only)"
INSTALL_DOCKER_CLI=0 APP_SLUG="$SLUG" docker compose build --pull=false backend frontend

echo "==> Building production images ${VERSION}"
docker build --pull=false -f release/Dockerfile.backend  --build-arg BASE_IMAGE=${SLUG}-backend:latest   -t "${SLUG}-backend:${VERSION}"  release
docker build --pull=false -f release/Dockerfile.web      --build-arg FRONTEND_IMAGE=${SLUG}-frontend:latest -t "${SLUG}-web:${VERSION}" release
docker build --pull=false -f release/Dockerfile.postgres -t "${SLUG}-postgres:${VERSION}" release

echo "==> Verifying no Python source in backend image"
n=$(docker run --rm --entrypoint sh "${SLUG}-backend:${VERSION}" -c 'find /app -name "*.py" | wc -l')
[ "$n" = "0" ] || { echo "ERROR: $n .py files left in image"; exit 1; }

echo "==> Packing ${OUT}"
rm -rf "$OUT"; mkdir -p "$OUT/images"
docker save "${SLUG}-backend:${VERSION}" "${SLUG}-web:${VERSION}" "${SLUG}-postgres:${VERSION}" | gzip -1 > "$OUT/images/${SLUG}-images-${VERSION}.tar.gz"
cp release/files/docker-compose.yml "$OUT/"
sed "s/__VERSION__/${VERSION}/" release/files/env.example > "$OUT/env.example"
cp release/files/nginx-site.conf "$OUT/"
cp release/DEPLOY.md "$OUT/"
echo "$VERSION" > "$OUT/VERSION"
( cd "$OUT" && sha256sum images/*.tar.gz docker-compose.yml env.example nginx-site.conf > SHA256SUMS )
tar -C dist -czf "dist/${SLUG}-${VERSION}.tar.gz" "${SLUG}-${VERSION}"
ls -lh "dist/${SLUG}-${VERSION}.tar.gz"
echo "==> Done: dist/${SLUG}-${VERSION}.tar.gz"
