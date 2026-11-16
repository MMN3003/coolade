#!/usr/bin/env bash
# Builds the production images and packs a source-free release bundle:
#   dist/ecocode-<version>/  (+ .tar.gz of that folder)
# Usage: release/build-release.sh [version]     (run from the repo root or release/)
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:-$(date +%Y.%m.%d)-$(git rev-parse --short HEAD)}"
OUT="dist/ecocode-${VERSION}"

echo "==> Building base images (dev compose, local layers only)"
INSTALL_DOCKER_CLI=0 docker compose build --pull=false backend frontend

echo "==> Building production images ${VERSION}"
docker build --pull=false -f release/Dockerfile.backend  --build-arg BASE_IMAGE=ecocode-backend:latest   -t "ecocode-backend:${VERSION}"  release
docker build --pull=false -f release/Dockerfile.web      --build-arg FRONTEND_IMAGE=ecocode-frontend:latest -t "ecocode-web:${VERSION}" release
docker build --pull=false -f release/Dockerfile.postgres -t "ecocode-postgres:${VERSION}" release

echo "==> Verifying no Python source in backend image"
n=$(docker run --rm --entrypoint sh "ecocode-backend:${VERSION}" -c 'find /app -name "*.py" | wc -l')
[ "$n" = "0" ] || { echo "ERROR: $n .py files left in image"; exit 1; }

echo "==> Packing ${OUT}"
rm -rf "$OUT"; mkdir -p "$OUT/images"
docker save "ecocode-backend:${VERSION}" "ecocode-web:${VERSION}" "ecocode-postgres:${VERSION}" | gzip -1 > "$OUT/images/ecocode-images-${VERSION}.tar.gz"
cp release/files/docker-compose.yml "$OUT/"
sed "s/__VERSION__/${VERSION}/" release/files/env.example > "$OUT/env.example"
cp release/files/nginx-site.conf "$OUT/"
cp release/DEPLOY.md "$OUT/"
echo "$VERSION" > "$OUT/VERSION"
( cd "$OUT" && sha256sum images/*.tar.gz docker-compose.yml env.example nginx-site.conf > SHA256SUMS )
tar -C dist -czf "dist/ecocode-${VERSION}.tar.gz" "ecocode-${VERSION}"
ls -lh "dist/ecocode-${VERSION}.tar.gz"
echo "==> Done: dist/ecocode-${VERSION}.tar.gz"
