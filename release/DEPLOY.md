# Coolade Gateway: Production Deployment Guide

This guide is for the DevOps engineer deploying Coolade Gateway on an existing Linux server that already runs nginx. The release contains **only prebuilt Docker images and configuration**. No source code is shipped. Inside the backend image the Python code is compiled bytecode only.

---

## 1. What you receive

```
coolade-<version>/
├── images/coolade-images-<version>.tar.gz   # 3 Docker images (backend, web, postgres)
├── docker-compose.yml                       # production stack
├── env.example                              # settings template -> .env
├── nginx-site.conf                          # site config for the host nginx
├── DEPLOY.md                                # this file
├── VERSION
└── SHA256SUMS
```

## 2. Architecture

```
Browser / Claude Code ──HTTPS──> host nginx :443  (TLS, your domain)
                                     │ proxy_pass http://127.0.0.1:8085
                                     ▼
                         ┌─ docker: coolade ─────────────────────────┐
                         │  web (nginx + built SPA)   127.0.0.1:8085 │
                         │     ├─ /api, /relay, /mcp ─> backend:8000 │
                         │  backend (FastAPI + Claude Code CLI)      │
                         │     └─> postgres:5432 (internal only)     │
                         └───────────────────────────────────────────┘
backend ──HTTPS──> api.anthropic.com  (outbound only)
```

* Only the host nginx is public. The app listens on `127.0.0.1:8085`, and postgres is not published at all.
* All AI traffic runs on **one Claude subscription login** (an OAuth file) that the backend reads from the host.

## 3. Server requirements

| Item | Minimum (14 users) | Recommended |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB | 40 GB SSD (DB, attachments, logs) |
| OS | Any 64-bit Linux with Docker | Ubuntu 22.04/24.04 LTS |
| Software | Docker Engine 24+ with Compose v2, nginx 1.18+ | |
| Network in | 443 (and 80 for redirect / Let's Encrypt) | |
| Network out | `api.anthropic.com:443`, `console.anthropic.com:443` (directly or via proxy) | |

Each concurrent chat runs one Claude Code process (about 0.5 to 1 GB RAM). `CLI_MAX_CONCURRENCY=4` fits 8 GB.

You also need:
* A DNS record (for example `ai.example.com`) pointing to the server.
* A TLS certificate for that name: Let's Encrypt, or your organization's own.
* A Claude subscription account to sign in with (step 5).

## 4. Load the release

```bash
# as a sudo-capable user
sudo mkdir -p /opt/coolade && sudo chown "$USER" /opt/coolade
tar -xzf coolade-<version>.tar.gz -C /opt/coolade --strip-components=1
cd /opt/coolade
sha256sum -c SHA256SUMS                      # every line must say OK
docker load -i images/coolade-images-*.tar.gz
docker images | grep coolade                 # coolade-backend / -web / -postgres : <version>
# (prefix is APP_SLUG used at build time; default coolade)
```

## 5. Sign in to the Claude subscription (once)

The backend container runs as **UID 1000**. Sign in as the host user with UID 1000 (check with `id -u`), so that it can read the file.

```bash
# as the UID-1000 user (e.g. "deploy")
curl -fsSL https://claude.ai/install.sh | bash      # or: npm i -g @anthropic-ai/claude-code  (Node 22+)
claude                                              # then type /login and follow the link
ls -l ~/.claude/.credentials.json                   # must exist, mode 600
```

* Use the account whose plan should be shared by all users.
* After the first start the backend refreshes the token itself. **Don't run the same login on two servers**: the refresh token rotates, so the two servers end up locking each other out.
* If the host has no direct internet access, set `HTTPS_PROXY` before running `claude`.

## 6. Configure `.env`

```bash
cd /opt/coolade
cp env.example .env && chmod 600 .env
```

Fill every `<...>` value:

```bash
python3 -c 'import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())'  # COOLADE_SECRET_KEY
openssl rand -hex 32   # SESSION_SECRET
openssl rand -hex 24   # POSTGRES_PASSWORD
openssl rand -hex 32   # INTERNAL_API_KEY
```

| Variable | Value |
|---|---|
| `APP_VERSION` | Already set to the release version. Must match the loaded image tag. |
| `APP_NAME` | Product name shown in the UI, page title and login (default `Coolade`). Can be changed any time; restart the backend. |
| `APP_SLUG` | Technical id (default `coolade`): image names, Docker volume prefix, cookie name, API key prefix `<slug>_live_`. Set it once before the first start. |
| `CLAUDE_CREDS_DIR` | Absolute path, e.g. `/home/deploy/.claude`. `~` does **not** work. |
| `ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD` | The first admin, created on first start only. Change the password in the UI later. |
| `COOKIE_SECURE` | `true` when the site is served over HTTPS (required for production). |
| `WEB_PORT` | `8085` by default. Change it if that port is taken; then also change `nginx-site.conf`. |
| `HTTPS_PROXY` | Only if outbound access to Anthropic needs a proxy. |

**Back up `.env`.** `COOLADE_SECRET_KEY` encrypts stored tokens. If you lose it, the encrypted data can't be read.

## 7. Start the stack

```bash
cd /opt/coolade
docker compose up -d
docker compose ps                      # postgres healthy, backend healthy, web running
curl -s http://127.0.0.1:8085/api/health
# {"status":"ok","db":true,...,"upstream_mode":"cli_creds","upstream_connected":true,"cli_available":true}
```

On first start the backend creates the database schema (migrations run automatically), the model catalog and the admin user. If `upstream_connected` is `false`, check step 5 (`docker compose logs backend | tail -50`).

## 8. Configure the host nginx

```bash
sudo cp /opt/coolade/nginx-site.conf /etc/nginx/sites-available/coolade.conf
sudo sed -i 's/ai.example.com/YOUR.DOMAIN/g' /etc/nginx/sites-available/coolade.conf
# adjust ssl_certificate / ssl_certificate_key if you don't use Let's Encrypt paths
sudo ln -s /etc/nginx/sites-available/coolade.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Notes:
* On RHEL-style nginx (no `sites-available`), copy the file to `/etc/nginx/conf.d/coolade.conf` instead.
* **Let's Encrypt:** run `sudo certbot certonly --webroot -w /var/www/html -d YOUR.DOMAIN` while only the port-80 server block is active, then enable the 443 block. Alternatively, `certbot --nginx -d YOUR.DOMAIN` edits the file for you.
* nginx older than 1.25 doesn't accept `http2 on;`. Remove that line and use `listen 443 ssl http2;` instead.
* If another site already defines a `map $http_upgrade ...`, keep the map in this file anyway. Its variable name is unique (`$coolade_connection_upgrade`).
* **Streaming must not be buffered.** Keep `proxy_buffering off` and the 900 s timeouts, or chat replies arrive all at once and long Claude Code requests get cut off.
* If a CDN or load balancer sits in front, also raise its timeouts (at least 600 s) and turn off response buffering there.

## 9. Verify (acceptance checklist)

| # | Check | Expected |
|---|---|---|
| 1 | `curl -sI https://YOUR.DOMAIN` | `200`, valid certificate |
| 2 | Open `https://YOUR.DOMAIN`, log in as the admin | Chat page loads. A login loop means `COOKIE_SECURE`/HTTPS is wrong. |
| 3 | Admin → **اتصال آپ‌استریم** (upstream connection) | Connected, auto-refresh active |
| 4 | Admin → **کاربران** → your user → **سیاست و سهمیه** (models and quota) | Tick models, set a quota (the admin starts with none) |
| 5 | Send a chat message on each model | Streams a reply |
| 6 | **کلیدهای API** (API keys) → create key; on a laptop: `ANTHROPIC_BASE_URL=https://YOUR.DOMAIN/relay ANTHROPIC_AUTH_TOKEN=<key> claude -p hi` | Replies |
| 7 | `curl -s -o /dev/null -w '%{http_code}' http://SERVER_IP:8085` from another machine | Connection refused (port not public) |

Before creating users, add models to the plans under **پلن‌ها** (plans). The built-in plans ship with no models.

## 10. Operations

**Logs**
```bash
docker compose logs -f backend        # app + Claude CLI
docker compose logs -f web            # inner nginx
tail -f /var/log/nginx/coolade.*.log  # host nginx
```
Container logs are rotated automatically (5 × 20 MB per service).

**Start / stop / restart**
```bash
docker compose stop        # keeps all data
docker compose up -d
docker compose restart backend
```
`restart: unless-stopped` brings the stack back after a reboot (Docker must be enabled: `sudo systemctl enable docker`).

**Backup** (daily cron recommended; volume names start with `APP_SLUG`, default `coolade`)
```bash
cd /opt/coolade
docker compose exec -T postgres pg_dumpall -U postgres | gzip > /backup/coolade-db-$(date +%F).sql.gz
for v in users_data teams_data attachments_data services_data claude_state; do
  docker run --rm --entrypoint tar -v coolade_$v:/v -v /backup:/b coolade-postgres:$(grep ^APP_VERSION= .env | cut -d= -f2) -czf /b/coolade-$v-$(date +%F).tgz -C /v .
done
cp .env /backup/coolade-env-$(date +%F)     # keep secure
```

**Restore** (on an empty stack)
```bash
docker compose up -d postgres
gunzip -c coolade-db-DATE.sql.gz | docker compose exec -T postgres psql -U postgres
for v in users_data teams_data attachments_data services_data claude_state; do
  docker run --rm --entrypoint tar -v coolade_$v:/v -v /backup:/b coolade-postgres:$(grep ^APP_VERSION= .env | cut -d= -f2) -xzf /b/coolade-$v-DATE.tgz -C /v
done
docker compose up -d
```

**Upgrade to a new release**
```bash
# 1. back up (above)
# 2. load the new images
docker load -i images/coolade-images-<new>.tar.gz
# 3. point .env to the new version, replace docker-compose.yml with the new one
sed -i 's/^APP_VERSION=.*/APP_VERSION=<new>/' .env
# 4. recreate (database migrations run automatically on backend start)
docker compose up -d
curl -s http://127.0.0.1:8085/api/health
```
To roll back, set the old `APP_VERSION` and run `docker compose up -d`. If the new release ran database migrations, restore the database backup taken before the upgrade.

**Claude login expired or revoked**
Admin → **اتصال آپ‌استریم** shows disconnected. Run `claude` and `/login` again as the UID-1000 user on the host. The backend picks up the changed file within about 60 s; you can also run `docker compose restart backend`.

## 11. Security notes

* Keep `BIND_ADDR=127.0.0.1`. Never publish 8085 or 5432 to the internet.
* `.env` and `~/.claude/.credentials.json` are secrets. Keep them at mode 600, out of git and out of tickets.
* The admin role can read every user's conversations. Give it to as few people as possible.
* API keys (`coolade_live_...`) are per user and can be revoked in the UI. Revoke any key that has been pasted in chat or email.
* `X-Forwarded-For` is set by the host nginx to the real client IP. The app uses it for login rate limiting, so don't let clients set it.

## 12. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Login succeeds then shows «لطفاً ابتدا وارد شوید» ("please log in first") | Site opened over `http://` while `COOKIE_SECURE=true`. Use `https://`. |
| Chat says «اجرای دستیار با خطا مواجه شد» ("the assistant failed to run") | `docker compose logs backend`. Usually the Claude login (step 5) or no outbound access to api.anthropic.com. |
| «این مدل برای شما مجاز نیست» (model not allowed for you) | The user or plan has no models ticked. |
| «سقف مصرف دوره تمام شده است» (usage limit for the period reached) | The user's quota is used up or not set. |
| Replies appear only at the end, or time out after 60 s | Buffering or timeouts in the host nginx or CDN (step 8). |
| `413 Request Entity Too Large` on upload | `client_max_body_size 60m` missing in the host nginx. |
| `backend` restarts in a loop | `docker compose logs backend`. Check the `.env` values, the DB password (changing `POSTGRES_PASSWORD` after first start needs the DB user's password changed too), and that `CLAUDE_CREDS_DIR` exists. |
| Claude Code on a laptop hangs | A `~/.claude/settings.json` `env` block on the laptop overrides `ANTHROPIC_BASE_URL`. Remove it. |
| Claude Code on a laptop shows «Select login method» | The laptop uses `ANTHROPIC_API_KEY` instead of `ANTHROPIC_AUTH_TOKEN`, the variable isn't exported in the shell rc file, or the first-run screen isn't marked done. See `docs/API-GUIDE.md` (or the in-app **اتصال CLI** page) for per-OS steps: macOS, Ubuntu, Windows, WSL. |
| `404`/`405` from a client | Its base URL is missing `/relay` or uses the removed `/v1` endpoints. Use `https://YOUR.DOMAIN/relay`. |
