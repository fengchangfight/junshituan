# 军师团 Ubuntu 生产部署指南

> 适用：Ubuntu 22.04 / 24.04 LTS。腾讯云轻量 4核4GB 起。

---

## 1. 初始部署

### 1.1 基础环境

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装基础工具
sudo apt install -y curl git ufw nginx certbot python3-certbot-nginx

# 配置防火墙
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 1.2 安装 Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker  # 或重新登录
docker --version
```

### 1.3 克隆代码

```bash
# 生成 SSH key（如已有可跳过）
ssh-keygen -t ed25519 -C "deploy@junshituan.com" -f ~/.ssh/junshituan_deploy

# 添加到 GitHub（复制公钥到 https://github.com/settings/keys）
cat ~/.ssh/junshituan_deploy.pub

# 配置 SSH
cat >> ~/.ssh/config << 'EOF'
Host github-junshituan
    HostName github.com
    IdentityFile ~/.ssh/junshituan_deploy
    IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config

# 克隆
mkdir -p /opt/junshituan
cd /opt
git clone git@github-junshituan:your-org/junshituan.git
```

### 1.4 迁移数据（从旧机器）

在旧机器上：

```bash
cd /path/to/junshituan
docker compose down
tar -czf junshituan-data.tar.gz docker/data/ backend/data/
scp junshituan-data.tar.gz ubuntu@新机器IP:/opt/junshituan/
```

在新机器上：

```bash
cd /opt/junshituan
tar -xzf junshituan-data.tar.gz
```

### 1.5 配置环境变量

```bash
cd /opt/junshituan
cp docker/.env.docker .env
```

编辑 `.env` 文件：

```env
# LLM（必填）
OPENAI_API_KEY=sk-your-deepseek-key
OPENAI_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro

# Embedding（本地模型，不需 API key）
LOCAL_EMBEDDING=true
LOCAL_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5

# JWT（必改）
JWT_SECRET=随机生成一个64位字符串

# 前端 API 地址（Nginx 代理后改为域名）
NEXT_PUBLIC_API_URL=https://junshituan.com
```

生成 JWT_SECRET：

```bash
openssl rand -hex 32
```

### 1.6 启动服务

```bash
cd /opt/junshituan

# 先只启动基础设施（数据库等）
docker compose up -d postgres etcd minio milvus attu

# 等健康检查通过后启动全部
docker compose up -d

# 确认全部运行
docker compose ps
```

首次启动会拉取镜像和下载嵌入模型，约 5-10 分钟。

### 1.7 创建管理员

```bash
curl -s -X POST http://localhost:8000/api/auth/admin/create \
  -H "Content-Type: application/json" \
  -d '{"username":"your-admin","password":"your-password"}'
```

### 1.8 配置 Nginx + SSL

创建 Nginx 配置：

```bash
sudo nano /etc/nginx/sites-available/junshituan
```

```nginx
# HTTP → HTTPS 重定向
server {
    listen 80;
    server_name junshituan.com;
    return 301 https://$host$request_uri;
}

# HTTPS
server {
    listen 443 ssl http2;
    server_name junshituan.com;

    # SSL 证书（certbot 自动填充）
    ssl_certificate     /etc/letsencrypt/live/junshituan.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/junshituan.com/privkey.pem;

    # 安全头
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;

    # 上传限制
    client_max_body_size 20M;

    # 前端
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;  # SSE 长连接
        proxy_buffering off;      # 流式输出不缓冲
    }

    # 后端 API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;  # SSE 长连接
        proxy_buffering off;
    }

    # Attu（Milvus GUI，可选）
    location /attu/ {
        proxy_pass http://127.0.0.1:8001/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
```

启用配置并申请 SSL：

```bash
sudo ln -s /etc/nginx/sites-available/junshituan /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t

# 申请 SSL 证书
sudo certbot --nginx -d junshituan.com

# 验证自动续期
sudo certbot renew --dry-run

# 启动 Nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

### 1.9 验证

浏览器访问 `https://junshituan.com`，确认：
- 页面正常加载
- 可以注册/登录
- 议事厅功能正常
- SSL 证书有效（浏览器地址栏显示锁图标）

---

## 2. 增量部署（日常更新）

### 2.1 标准流程

```bash
cd /opt/junshituan
git pull

# 仅重新构建有变更的服务
docker compose build backend frontend
docker compose up -d --no-deps backend frontend

# 验证
docker compose ps
```

### 2.2 完整重建（依赖变更时）

```bash
cd /opt/junshituan
git pull
docker compose build --no-cache backend frontend
docker compose up -d
```

### 2.3 数据库迁移

项目在 `init_db()` 中自动执行 PostgreSQL `ADD COLUMN IF NOT EXISTS` 迁移，无需手动运行。出现数据库错误时检查后端日志：

```bash
docker compose logs backend | tail -50
```

### 2.4 回滚

```bash
git log --oneline -5          # 找到上一个稳定版本
git checkout <commit-hash>
docker compose build backend frontend
docker compose up -d --no-deps backend frontend
```

---

## 3. 运维

### 3.1 常用命令

```bash
# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f backend
docker compose logs -f --tail 100

# 重启单个服务
docker compose restart backend

# 数据备份
cd /opt/junshituan
tar -czf backup-$(date +%Y%m%d).tar.gz docker/data/ backend/data/

# 磁盘使用
df -h
docker system df
```

### 3.2 内存监控

腾讯云轻量 4GB 内存下，设置 swap 防 OOM：

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 3.3 定时备份（cron）

```bash
# 每天凌晨 3 点备份数据
crontab -e
# 添加：
0 3 * * * cd /opt/junshituan && tar -czf backup-$(date +\%Y\%m\%d).tar.gz docker/data/ backend/data/ && find . -name 'backup-*.tar.gz' -mtime +7 -delete
```

---

## 4. 检查清单

| 项 | ✅ |
|---|---|
| SSH key 配置，可免密拉取 Git | |
| `.env` 中 `JWT_SECRET` 已修改 | |
| `.env` 中 `OPENAI_API_KEY` 已填入 | |
| `NEXT_PUBLIC_API_URL` 指向域名 | |
| Docker 服务全部 healthy | |
| 管理员账号已创建 | |
| Nginx SSL 证书生效 | |
| `proxy_buffering off` 确保 SSE 流式正常 | |
| `proxy_read_timeout 300s` 确保长连接不断 | |
| Swap 已配置 | |
| 定时备份已启用 | |
