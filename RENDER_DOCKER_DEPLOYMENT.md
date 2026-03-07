# Render Docker Deployment (Production)

This project is configured for Docker-based deployment on Render with:
- Python 3.11
- FFmpeg installed in container
- yt-dlp + audio extraction support
- Shazam recognition support
- Webhook mode for Telegram bot
- Separate web and worker services

## 1) Prerequisites

- Render account
- Telegram bot token
- PostgreSQL database URL
- Redis URL (and ARQ Redis URL)
- Public webhook URL (Render service URL)

## 2) Files Used

- `Dockerfile` (runtime image with FFmpeg)
- `render.yaml` (web + worker blueprint)
- `.env.example` (environment template)
- `requirements.txt` (Python dependencies)

## 3) Deploy Steps

1. Push this repository to GitHub/GitLab.
2. In Render, create service from Blueprint (`render.yaml`).
3. Set required environment variables in Render:
   - `BOT_TOKEN`
   - `DATABASE_URL`
   - `REDIS_URL`
   - `ARQ_REDIS_URL`
   - `WEBHOOK_HOST` (must be your Render web URL, e.g. `https://savedbot-web.onrender.com`)
4. Deploy web service (`savedbot-web`).
5. Deploy worker service (`savedbot-worker`).
6. Confirm webhook mode is active from logs:
   - `Starting Webhook server on port ...`
   - `Setting webhook: https://.../webhook`

## 4) Verify FFmpeg in Container

Use Render Shell on the running web service and run:

```bash
ffmpeg -version
ffprobe -version
python -c "import shutil; print(shutil.which('ffmpeg'))"
```

Expected:
- `ffmpeg`/`ffprobe` version output
- path like `/usr/bin/ffmpeg`

## 5) Runtime Health Checks

Health endpoint:
- `GET /health` returns `200 OK`

Quick checks:

```bash
curl -i https://<your-render-domain>/health
curl -i https://<your-render-domain>/
```

## 6) Debug: FFmpeg Not Found

If audio extraction fails and logs mention FFmpeg:

1. Check binary in shell:
   - `which ffmpeg`
   - `ffmpeg -version`
2. Verify environment:
   - `echo $FFMPEG_BINARY` (should be `/usr/bin/ffmpeg` in container)
3. Confirm Docker image is the latest:
   - trigger full rebuild (Clear build cache + deploy)
4. Confirm service uses Docker blueprint, not native Python build.
5. Verify `Dockerfile` contains:
   - `apt-get install ... ffmpeg ...`

## 7) Debug: `shazamio-core` / maturin Error

If deploy logs show:
- `metadata-generation-failed`
- package: `shazamio-core`
- `Read-only file system (os error 30)`
- interpreter path like `.venv/bin/python3.14`

Fix:
1. Deploy via Docker (`render.yaml`) instead of native Python runtime.
2. Pin Python to 3.11 (`runtime.txt` is set to `python-3.11.11`).
3. Keep writable cargo env vars:
   - `CARGO_HOME=/tmp/cargo`
   - `RUSTUP_HOME=/tmp/rustup`
4. Clear build cache and redeploy once.

## 8) Webhook-Only Production Mode

Webhook mode is enabled when `WEBHOOK_HOST` is set.
If `WEBHOOK_HOST` is missing, app falls back to polling (not recommended on Render production).

Set:
- `WEBHOOK_HOST=https://<your-render-domain>`
- `WEBHOOK_PATH=/webhook`

## 9) Performance and Scale Tips (500k+ users)

- Use paid Render plans (`starter`/`standard`) for both web and worker.
- Keep web and worker separated (already configured).
- Use managed PostgreSQL + Redis with low latency region.
- Increase worker concurrency gradually:
  - tune `max_jobs` in `bot/services/worker.py`
- Use webhook mode only (already configured by env).
- Add monitoring/alerts on:
  - webhook latency
  - queue lag
  - Redis memory
  - DB connections
- Consider object storage/CDN for large media workflows.

## 10) Security Checklist

- Never commit real `.env` or tokens.
- Keep `BOT_TOKEN` only in Render env vars.
- Run as non-root user in container (already configured).
- Use HTTPS webhook only.
- Restrict admin IDs via env.
