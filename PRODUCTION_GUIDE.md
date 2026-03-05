# 🚀 Production Deployment & Scaling Guide

This guide provides technical recommendations for deploying and scaling the bot to support **500,000+ users**.

## 1. Cloud Architecture Recommendation (VPS/Dedicated)

For a high-load bot, we recommend a **Distributed Architecture**:

| Resource | Recommendation | Specs |
| :--- | :--- | :--- |
| **Main Bot (Webhook)** | Hetzner CCX22 or DigitalOcean Droplet | 4 vCPU, 8GB RAM |
| **Worker Nodes** | 2-3 Dedicated Instances | 8 vCPU, 16GB RAM + High NVMe |
| **Database** | Managed PostgreSQL (Neon/Supabase/RDS) | 2 vCPU, 4GB RAM |
| **Redis** | Managed Redis or Dedicated Cluster | 2 vCPU, 4GB RAM |

## 2. Scaling Strategy

### Vertical Scaling
- Increase CPU/RAM for the aiohttp/webhook server.
- Webhook mode is significantly faster than polling and uses fewer resources per request.

### Horizontal Scaling
- **Multiple Workers**: You can run 5-10 instances of the `worker.py` (arq) on different servers. They all listen to the same Redis queue.
- **Queue Prioritization**: Use separate Redis queues by task type (e.g., downloads vs analytics) to keep critical tasks responsive.
- **Read Replicas**: Use PostgreSQL read replicas for the Admin panel and stats to reduce load on the primary DB.

## 3. High-Load Optimizations

- **URL Normalization**: Reduces redundant downloads by 40-60%.
- **file_id System**: Reusing Telegram file IDs saves bandwidth and time.
- **Nginx Reverse Proxy**:
    ```nginx
    location /webhook {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    ```
- **Connection Pooling**: `asyncpg` with a pool of 20-50 connections.

## 4. Production Checklist

- [ ] Change `BOT_TOKEN` and `DATABASE_URL` to production secrets.
- [ ] Enable `sslmode=require` for PostgreSQL.
- [ ] Configure Redis persistence (RDB + AOF).
- [ ] Set up external monitoring (Sentry, Prometheus/Grafana).
- [ ] Set up daily database backups.
- [ ] Verify `FFmpeg` and `yt-dlp` are the latest versions.
- [ ] Ensure `DOWNLOAD_DIR` is on a fast NVMe partition.
- [ ] Increase `soft nofile` limits on Linux.
