# 服务器运行指南

运行位置为 `124.220.147.193`，日常管理用户为 `weiyu`。前端由 GitHub Pages 发布，服务器仅提供 API。以下是需要有权限的操作者执行的部署步骤，不代表服务已经安装、启动或通过线上验收。

## 端口、目录和身份

| 项目 | 配置 |
| --- | --- |
| 公网入口 | 80（ACME 验证、HTTPS 跳转）、443（API） |
| 后端 | `127.0.0.1:8000`，systemd 用户 `weiyu` |
| PostgreSQL | `127.0.0.1:5432`，不向公网发布 |
| 应用代码 | `/srv/studyloop/app` |
| 后端虚拟环境 | `/srv/studyloop/venv` |
| 头像持久化目录 | `/srv/studyloop/data/avatars` |
| 后端私有配置 | `/etc/studyloop/backend.env`，属主 root、组 weiyu、模式 0640 |
| 数据库数据 | 系统 PostgreSQL 的独立数据目录；不在应用代码目录 |
| ACME webroot | `/var/lib/studyloop/acme` |
| Certbot 环境 | `/opt/studyloop-certbot` |

平台注册账号与 Linux 用户无关。首次部署需系统安装、Nginx、systemd 和云网络配置权限；`weiyu` 的 sudo 需要认证，可由已有管理员完成初始化。不改动 SSH 或 Clash 的配置，不通过关闭它们处理路由。

## 首次安装

先以 `python3 --version` 确认系统 Python 为 3.12 或更新版本；其余开发环境要求见 [README](../README.md)。系统版本不满足时先安装受支持的 Python，再用对应解释器创建虚拟环境。

先确认云安全组允许 TCP 80/443，保留现有 SSH 规则。操作前检查已有端口和 PostgreSQL 集群，避免覆盖已有服务。以下针对尚未安装的 Ubuntu 环境：

```bash
sudo apt-get update
sudo apt-get install python3-venv postgresql nginx git
sudo install -d -o weiyu -g weiyu /srv/studyloop /srv/studyloop/data/avatars
sudo install -d -m 0755 /etc/studyloop /var/lib/studyloop/acme
sudo install -d -m 0755 /usr/local/libexec
```

PostgreSQL 配置以 `pg_lsclusters` 找到实际集群，使用 `sudo -u postgres psql -c 'SHOW config_file'` 确定配置文件。将 `listen_addresses` 设为 `127.0.0.1`；`pg_hba.conf` 仅允许需要的本机连接，认证使用 `scram-sha-256`，不设置公网或 `trust` 规则。重启对应集群并检查实际监听。

仅在应用角色和数据库尚不存在时执行：

```bash
sudo -u postgres createuser --pwprompt studyloop
sudo -u postgres createdb --owner=studyloop studyloop
```

为应用设置独立数据库密码；应用角色不授予超级用户或创建其他角色的能力。在实际连接 URL 中对密码的特殊字符进行 URL 编码。

以 `weiyu` 将经过审查并合并的代码放入 `/srv/studyloop/app`；首次可运行 `git clone https://github.com/njuywy/StudyLoop.git /srv/studyloop/app`。不要将本地 `.env`、开发虚拟环境、浏览器产物或测试报告上传到应用目录。

以管理员建立配置文件：

```bash
sudo install -o root -g weiyu -m 0640 /srv/studyloop/app/backend/.env.example /etc/studyloop/backend.env
sudoedit /etc/studyloop/backend.env
```

配置 `DATABASE_URL=postgresql://studyloop:<URL编码后的密码>@127.0.0.1:5432/studyloop`，生产 `CORS_ORIGINS=https://njuywy.github.io`；头像目录保留 `/srv/studyloop/data/avatars`。注册、验证和重发需要下面的 SMTP 配置。不可把配置提交、输出至工单或传入前端构建。

以 `weiyu` 安装后端及执行迁移：

```bash
python3 -m venv /srv/studyloop/venv
/srv/studyloop/venv/bin/python -m pip install --require-hashes -r /srv/studyloop/app/backend/requirements.lock
/srv/studyloop/venv/bin/python -m dotenv -f /etc/studyloop/backend.env run -- /srv/studyloop/venv/bin/alembic -c /srv/studyloop/app/backend/alembic.ini upgrade head
```

requirements.lock 来源于已提交 uv.lock；维护依赖时通过 `uv export --project backend --frozen --no-dev --no-emit-project --format requirements-txt --output-file backend/requirements.lock` 一并更新，部署时不临时选择最新版本。

启用 API：

```bash
sudo install -m 0644 /srv/studyloop/app/deploy/studyloop-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now studyloop-api
curl --fail http://127.0.0.1:8000/api/v1/health
```

健康响应应为 `{"status":"ok","database":"ok"}`；数据库故障为 503、安全 code/message。不要用关闭数据库作为公网隔离的验收方式。

## 邮件服务与注册

在 `/etc/studyloop/backend.env` 私有文件中配置邮件服务。现有配置文件应逐项补充，不能用示例覆盖已有数据库凭据。

| 配置 | 用途与默认值 |
| --- | --- |
| `SMTP_HOST`、`SMTP_FROM` | 必填：服务地址、服务商允许的发件邮箱 |
| `SMTP_PORT`、`SMTP_TLS_MODE` | 默认 587/starttls；隐式 TLS 使用 465/ssl，按服务商要求配置；不允许明文模式 |
| `SMTP_USERNAME`、`SMTP_PASSWORD` | 需要认证时一起填写；密码通常是 SMTP 专用授权码，不是网页登录密码 |
| `SMTP_TIMEOUT` | 每次 socket 操作默认 5 秒，允许大于 0 且不超过 10 秒 |
| `PAGES_URL` | 默认 `https://njuywy.github.io/StudyLoop/`；必须是带末尾 `/` 的 HTTPS 基础地址，无 query/hash |
| `REGISTER_LIMIT`、`RESEND_LIMIT` | 每客户端 IP、10 分钟窗口分别最多 10/20 次有效格式请求，可设置正整数 |

邮件地址去除首尾空白并统一小写；当前仅接受无需 SMTPUTF8 的邮箱地址。昵称空白默认“学习者”，密码保留空格且按 Unicode 字符计数。账号的邮箱验证、启用和角色独立；注册不授予管理员，也不产生登录会话。密码使用 Argon2id；邮箱令牌只存 SHA-256 摘要，24 小时有效且单次消费。登录与会话复用 `users.id`，不得重新定义账号身份。

重发请求另有按归一化邮箱的 60 秒冷却，存在和不存在的邮箱都计数；成功注册发信后 60 秒内不会再次投递。入口限流记录保存在 PostgreSQL，进程重启仍生效，过期记录随请求清理。Nginx 覆盖 X-Forwarded-For，Uvicorn 仅信任 loopback 代理，不应扩大受信代理范围。

重发统一返回 202 受理，不能据此判断账号是否存在、已验证或禁用，也不能据此确认邮件已送达。页面以中性提示说明“若未收到或发送失败，请 60 秒后重试”；只对符合条件的待验证账号尝试投递，其他地址不联系 SMTP。发送失败不会删除账号或替换旧有效令牌；重试遵守同样的 60 秒冷却。注册发信失败会明确提示使用重发入口，待验证账号仍保留；重复注册不覆盖已有账号。此取舍由操作者确认，以保护邮箱存在性，包括 SMTP DATA 阶段失败。

升级时先安装 `requirements.lock`，运行 Alembic `upgrade head`，再重启 API。同步更新 Nginx 的 `proxy_read_timeout 120s` 并通过 `nginx -t` 后 reload，以容纳 TLS、认证与投递的多个 socket 操作；前端等待最长 125 秒。不要在生产启用 SMTP debug、记录请求体或完整验证链接。

以受控邮箱在 Pages 注册，实际收件后打开 `#/verify-email?token=…`，点击确认验证，验证成功不会自动登录。故障验收与手机复核以 [Ticket #3](https://github.com/njuywy/StudyLoop/issues/3) 的 TC-07 为准；测试邮件边界及模拟浏览器不能代替生产 TLS/认证和真实收件。

## 登录与会话

`0003_sessions` 迁移建立 `auth_sessions` 表和账号变为禁用或未验证时撤销会话的数据库规则。会话使用随机 Bearer token；数据库只保存 SHA-256 摘要，默认 12 小时有效。`GET /api/v1/me` 每次查询当前会话及账号验证、启用状态；退出在服务端撤销当前会话。账号禁用后旧会话不会因恢复账号而重新生效。前端只在当前标签页的 `sessionStorage` 保存 token 和到期时间，收到 401 或到期后清理并转向登录；网络错误保留会话供重试。API 与浏览器响应不写入原始 token、密码摘要或其他用户会话。

`LOGIN_LIMIT` 默认每客户端 IP 在 10 分钟内最多 10 次尝试，与注册/重发共用 PostgreSQL 限流表。登录失败对错误密码、未验证、禁用和不存在账号返回统一的安全提示；限流返回 429。生产数据库不运行用例；由操作者提供已运行的隔离 `TEST_DATABASE_URL` 后执行真实 PostgreSQL 会话测试。登录页面、受保护复习页和个人中心的实际线上手机验收以 [Ticket #4](https://github.com/njuywy/StudyLoop/issues/4) 为准。

## 首次 HTTPS 签发

IP 证书需要 Certbot 5.4+ 的 `--ip-address` 与短期 profile。本示例隔离安装最低支持版本；更换版本需确认兼容并记录实际版本，不覆盖系统其他 Certbot 服务。

```bash
sudo python3 -m venv /opt/studyloop-certbot
sudo /opt/studyloop-certbot/bin/python -m pip install 'certbot==5.4.0'
sudo install -m 0644 /srv/studyloop/app/deploy/nginx-http.conf /etc/nginx/sites-available/studyloop
sudo ln -s /etc/nginx/sites-available/studyloop /etc/nginx/sites-enabled/studyloop
sudo nginx -t
sudo systemctl reload nginx
```

如果是新安装 Nginx，检查系统默认站点是否与目标端口冲突，仅调整系统初始默认站点；不要删除已有业务配置。先在外部网络确认 `http://124.220.147.193/.well-known/acme-challenge/` 下的实际探测文件能够取回，探测完成删除该文件。

首次先请求 staging，成功后使用生产环境；将 `--email` 参数替换为操作者自己的通知邮箱：

```bash
sudo /opt/studyloop-certbot/bin/certbot certonly --staging --cert-name studyloop-ip-staging --preferred-profile shortlived --webroot --webroot-path /var/lib/studyloop/acme --ip-address 124.220.147.193 --agree-tos --email '<通知邮箱>'
sudo /opt/studyloop-certbot/bin/certbot certonly --cert-name 124.220.147.193 --preferred-profile shortlived --webroot --webroot-path /var/lib/studyloop/acme --ip-address 124.220.147.193 --agree-tos --email '<通知邮箱>'
```

不要把 staging 证书用于生产 Nginx。生产签发成功后确认 `/etc/letsencrypt/live/124.220.147.193/` 中的证书与私钥存在，再切换 HTTPS 配置：

```bash
sudo install -m 0644 /srv/studyloop/app/deploy/nginx.conf /etc/nginx/sites-available/studyloop
sudo nginx -t
sudo systemctl reload nginx
curl --fail https://124.220.147.193/api/v1/health
```

不得使用 `curl -k` 或在浏览器忽略证书错误通过验收。Nginx 仅代理 `/api/v1/`，不将头像磁盘目录或后端配置作为公共静态目录。当前 3 MiB 的请求上限为后续 2 MiB 头像加 multipart 开销预留，不代表后端允许超限头像。

## 自动续期

IP 证书有效期约六天，必须自动续期。安装成功续期后的 Nginx 检查/重载 hook，以及每十二小时加随机延迟的任务：

```bash
sudo install -m 0755 /srv/studyloop/app/deploy/reload-nginx.sh /usr/local/libexec/studyloop-reload-nginx
sudo install -m 0644 /srv/studyloop/app/deploy/studyloop-certbot.service /etc/systemd/system/
sudo install -m 0644 /srv/studyloop/app/deploy/studyloop-certbot.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now studyloop-certbot.timer
sudo /opt/studyloop-certbot/bin/certbot renew --cert-name 124.220.147.193 --dry-run
sudo /usr/local/libexec/studyloop-reload-nginx
sudo systemctl list-timers studyloop-certbot.timer
```

dry-run 证明续期验证流程，不表示已经发生生产续期；单独运行 hook 检查重载。staging 试签的证书会保留在 Certbot 配置中，验证完成后以 `certbot delete --cert-name studyloop-ip-staging` 清理该**测试证书**，使定时任务只管理需要续期的生产证书。不删除其他站点证书。

## 更新与持久化

应用代码更新、锁文件安装和迁移完成后，再执行 `sudo systemctl restart studyloop-api` 并检查健康响应。数据库目录和 `/srv/studyloop/data/avatars` 不在 Git 发布目录内，更新代码时不删除它们。应用启动不自动迁移，避免多进程启动时修改 schema；迁移失败则停止发布，不重置数据。

新迁移通过 Alembic 创建并审查，保持现有版本链；升级重复运行应保持相同版本。需要回退时先判断 schema 是否兼容旧代码，不机械执行破坏性 downgrade。

## Pages 与公网验收

仓库 Settings → Pages 的 Source 设为 GitHub Actions。`CI and Pages` 在 `main` 的前后端检查通过后发布前端；PR 只执行检查，不能把预览或 PR 绿灯当成主站上线证据。前端构建变量只含公开 API 地址。

人工验收的权威用例仍是 Ticket #2：

1. 桌面与手机打开 `https://njuywy.github.io/StudyLoop/`，点击导航进入 hash 页面并刷新，页面不应 404；未交付功能显示准备中（TC-01）。
2. 浏览器检查 health 请求来自 `https://124.220.147.193/api/v1/health`、返回正常，无 mixed-content 或证书错误。用正确和其他 Origin 验证预检；后者不获允许（TC-04）。
3. 记录可信 IP 证书、dry-run、hook、定时任务与 SSH/Clash 仍可用的证据（TC-06）。
4. 服务器内部数据库正常、外部 HTTPS API 可达时，检查实际 PostgreSQL 监听、端口映射与云网络规则；从外部网络探测实际数据库端口，必须无法建立连接（TC-08）。API 与数据库同时不可达不能算通过。
5. 重启应用与对应数据库服务后，已有迁移版本与持久化数据保持；使用隔离测试数据验证，勿修改生产业务记录（TC-05）。

不要在操作记录、Actions 日志或工单中写入私钥、数据库密码或 SMTP 认证信息。

依据：[GitHub Pages/Vite](https://vite.dev/guide/static-deploy.html#github-pages)、[Let’s Encrypt IP 证书与 Certbot](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)、[Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html)。
