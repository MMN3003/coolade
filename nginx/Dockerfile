FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY html/ /usr/share/nginx/html/

# /usr/share/nginx/html is mounted as a named volume in docker-compose so a
# later frontend build (Dev2, out of this Dockerfile's scope) can populate it
# with the real SPA without rebuilding this image. Docker pre-seeds a fresh
# named volume from the image's existing directory content, so this
# placeholder page serves correctly until then.
