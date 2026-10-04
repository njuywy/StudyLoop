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

## 密码重置与凭据撤销

忘记密码入口为 `#/forgot-password`，邮件指向 `#/reset-password?token=…`。仅已验证且启用账号会收到重置邮件，链接有效期 30 分钟，必须主动提交 12～128 字符的新密码。`PASSWORD_RESET_LIMIT` 默认按客户端 IP 在 10 分钟内限制 10 次申请；所有账号资格和 SMTP 失败均返回同一受理提示，不能据此确认邮箱存在或邮件送达。复用现有 SMTP 配置和 `email_tokens` 表的 `reset_password` 用途，无额外数据库迁移。

成功发送的新链接替代旧链接；SMTP 失败或超时保留旧有效链接。发信替换、重置消费及密码修改必须先取得同一 `users` 行锁，再操作令牌和会话，避免并发恢复旧链接。`passwords.replace_password_and_revoke` 供密码重置与密码修改复用，调用者须在同一事务中持有账号行锁并完成自身资格校验；该函数更新密码摘要、撤销全部会话并消费全部未使用的重置令牌，不自行提交。任何一步失败都由事务回滚。

生产收件与重新登录按 [Ticket #5](https://github.com/njuywy/StudyLoop/issues/5) TC-07 验收。浏览器测试使用模拟 API，真实 PostgreSQL 的锁竞争与回滚用例必须连接操作者提供的已有隔离测试库；不要在生产库运行测试。日志中不得加入完整重置链接、令牌或新密码。

## 用户自助资料维护

个人中心允许修改昵称与密码，邮箱保持只读。`PATCH /api/v1/me` 只接收昵称，trim 后为 1～30 字符；`POST /api/v1/me/change-password` 必须验证旧密码，新密码为 12～128 字符且保留空格。改密成功后全部会话与未使用重置链接失效，前端引导使用新密码重新登录。错旧密码返回安全的 400，保持当前会话供重试。

受保护的写操作使用 `sessions.lock_current_user`：先锁账号，再重新检查会话与账号资格，防止请求等待账号锁期间被改密、重置或禁用后继续写入。密码修改复用上节的事务内撤销操作。昵称、账号身份和密码的状态仅依据服务端会话，客户端提交的 ID、邮箱、角色或启用字段被拒绝。真实设备与故障交互验收见 [Ticket #6](https://github.com/njuywy/StudyLoop/issues/6)。

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

## 私有头像

`0004_avatar` 为账号增加当前头像文件引用。升级时安装锁定的 Pillow 与 multipart 依赖并执行迁移；`AVATAR_DIRECTORY` 默认 `/srv/studyloop/data/avatars`，必须持久化并允许 API 账号读写。文件按账号 UUID 分目录，文件名由服务器随机生成，不使用上传文件名。不要将该目录设为 Nginx 静态目录；备份与恢复时保持数据库及头像目录的一致性。

`GET/PUT /api/v1/me/avatar` 均要求当前有效会话，PUT 使用 multipart 的 `file` 字段，只接受实际可解码且 MIME 相符的 JPEG/PNG/WebP。文件最多 2,097,152 字节（不含 multipart 包装），Nginx `client_max_body_size 3m` 保留包装余量。解码累计最多 1600 万像素、最多 32 帧；前端默认头像不会替代上传验证。读取不存在头像返回 `404 NO_AVATAR`，响应不缓存，也不返回磁盘路径。

上传先在账号行锁内写入独立候选文件并同步内容，再提交数据库引用；读取也在同一锁内完成，避免读取与替换清理竞态。普通写入/事务失败保留原引用，清理未引用候选；成功后清理旧文件。清理会重新加锁读取当前引用，避免误删并发上传或“提交成功但确认响应丢失”的当前文件。若数据库或目录暂不可用，记录不含路径的延后清理警告，下一次上传自动重试。提交结果不确定时前端提示失败，重新读取确认当前图像，不承诺跨数据库与文件系统的原子提交。

前端通过认证 fetch 取得 Blob，导航与个人中心共享显示；更换、退出、401 和切换账号时释放旧 object URL，迟到的旧账号请求不能覆盖新账号。真实文件系统/数据库故障与并发测试需要已有隔离测试库；真实手机文件选择、服务重启后头像持久化按 [Ticket #7](https://github.com/njuywy/StudyLoop/issues/7) 验收。

## 管理员与账号状态

平台管理员是数据库中的角色，与 Linux 的 `weiyu`/`ubuntu` 无关。先通过注册邮件验证一个启用的账号，再由有后端配置访问权限的运维者以 `weiyu` 执行：

```bash
cd /srv/studyloop/app/backend
PYTHONPATH=src /srv/studyloop/venv/bin/python -m dotenv -f /etc/studyloop/backend.env run -- /srv/studyloop/venv/bin/python -m studyloop.cli grant-admin verified@example.com
```

将示例邮箱换为已验证账号。命令按注册规则规范化邮箱，只对已验证且启用账号授予管理员；重复执行幂等成功，不存在、未验证或禁用时退出码为 1，参数错误为 2。不会输出数据库连接、密码或令牌。没有公开 HTTP 授权角色接口，也不通过网页修改角色或删除账号。已登录会话会在下一次资料/管理请求时读取新角色；刷新个人中心后可从导航进入“用户管理”，地址 `#/admin/users`。

`GET /api/v1/admin/users` 接受 `page`（从 1 起）和 `page_size`（默认 20，1～100），按注册时间、ID 稳定排序，同一 SQL 快照返回总数与该页；空页仍返回总数。只展示 ID、邮箱、昵称、角色、验证/启用状态与注册时间，不包含密码摘要、头像路径或各类 token。所有管理请求都会在锁内再次检查会话、账号状态与当前管理员角色。

`PATCH /api/v1/admin/users/{id}/status` 仅接受布尔 `enabled`，仅允许普通用户目标；管理员（含自身）受保护。禁用复用 `0003_sessions` 数据库触发器，在同一事务撤销全部会话；恢复不恢复旧会话，必须用当前有效密码重新登录。重复禁用/恢复保持稳定；锁按用户 ID 顺序取得以避免管理员相互操作死锁。不新增迁移，部署代码后重启服务即可。

线上角色与实际命令验收按 [Ticket #8](https://github.com/njuywy/StudyLoop/issues/8) TC-07，使用管理员 M、普通 A/B 的独立浏览器上下文。此命令交付不代表已替某个生产账号授予角色；需选定实际已验证邮箱。测试命令、禁用及故障注入只针对操作者提供的已有隔离测试数据库。

## 私有复习资料

复习资料由运维在网页之外导入。`0005_review_content` 保存资料、目录与知识点的结构化内容；`REVIEW_DIRECTORY` 默认 `/srv/studyloop/data/review`，用于不可变 PDF/图片资源包，API 账号只需读取。该路径不能作为 Nginx 静态目录或 Pages 发布目录，源 PDF、提取内容及 coverage 文件不得加入公开仓库。现有 systemd 保护允许读取这里；导入由 `weiyu` 在服务进程外执行，不需放宽 API 的只读文件系统。

本地准备首章（在仓库根目录，输出路径必须尚不存在）：

```bash
PYTHONPATH=backend/src uv run --project backend python -m studyloop.content_import build \
  docs/案例冲刺宝典.pdf /tmp/studyloop-private-chapter1 \
  --start-page 21 --end-page 48 --title 案例冲刺宝典
PYTHONPATH=backend/src uv run --project backend python -m studyloop.content_import validate \
  /tmp/studyloop-private-chapter1
```

构建采用 [PyMuPDF 的文字、图像和表格接口](https://pymupdf.readthedocs.io/en/latest/page.html)，按 PDF 书签实际标题位置切分，而不是按页平均切分。正文换行合并，父节点引言保留；复杂表格、嵌入图像以高清局部图保留原版关系。`manifest.json` 保存稳定 ID、正文块锚点、来源与资源校验值，`coverage.json` 记录各来源行归为标题、正文、图表、页眉页脚或斜向水印，供对照核验。当前工具针对本次有文字/书签的资料；无法定位标题、空叶节点和未归属正文会终止构建，不假装完成。其他版式需核对后再适配。

安装锁定依赖、执行 `alembic upgrade head` 后，将经核对的完整资源包通过 SSH 上传到服务器私有临时目录，再执行：

```bash
sudo install -d -m 0700 -o weiyu -g weiyu /srv/studyloop/data/review
cd /srv/studyloop/app/backend
PYTHONPATH=src /srv/studyloop/venv/bin/python -m dotenv -f /etc/studyloop/backend.env run -- \
  /srv/studyloop/venv/bin/python -m studyloop.content_import publish /tmp/studyloop-private-chapter1
sudo systemctl restart studyloop-api
```

发布先验证源文件与所有资源校验值，再创建不可变版本目录，最后在数据库事务和资料级锁内切换引用。相同资源包可以重跑；追加章节须包含此前已发布知识点，保持原 ID/锚点，不能退回仅含部分旧内容的包。导入失败不删除已发布资源；确认结果不明时重新读取数据库引用，不删候选。历史和失败候选可能留在私有目录，核实数据库及备份没有引用后才由运维清理，不在请求中自动删资源。

备份时先备份数据库，再备份包含旧/新版本的整个复习资源目录；清理旧包期间不得执行此流程。恢复到既有隔离环境时同时还原数据库与对应版本目录，保持目录 `0700`、文件 `0600` 和 API 账号所有权，然后验证目录、知识点、图表与原文都可通过认证接口读取。不要用破坏性数据库降级或覆盖生产数据验证恢复。

部署核查：有效登录后读取 `/api/v1/review/books` 和目录，打开首章、放大图表、对照来源页；未登录请求资料、正文、图片、PDF 和原页均应拒绝。响应使用 `Cache-Control: no-store`，前端以带会话的请求读取图片 Blob 并在退出/换号后释放。阅读深链接使用 `#/review?book=资料ID&point=知识点ID`，兼容原有登录返回白名单。完整内容与真实设备验收记录在相应 Ticket，缺少隔离 PostgreSQL 连接时不能宣称已验证迁移/事务。

完整资料发布使用同一源文件，构建范围改为 `--start-page 15 --end-page 305`，其余命令相同。第 1 页封面书签作为资料根，不生成空知识点；第 2～14 页印刷目录由可操作目录替代，原始 PDF 仍完整保留 305 页。其余 337 个书签全部映射为目录或正文入口。跨行标题定位跳过夹在行间的斜向水印；本资料的 Courier 代码片段保留为可放大的局部图，以保留原始缩进与换行，普通正文继续重排。导入前比较已发布首章的知识点 ID、正文锚点及块内容，不得因扩充重置私人引用。

浏览器目录支持不区分英文字母大小写的标题搜索，结果显示上级路径；纯目录结果展开对应分支，有正文的结果进入知识点。搜索不包括全文，也不改变资料顺序或用户状态。全书覆盖自动校验与人工图文核对分别记录在 Ticket #27，不把自动映射成功视为语义校对完成。


阅读位置由迁移 `0006_reading_position` 增加的 `review_positions` 与 `review_position_operations` 保存，随 PostgreSQL 一起备份和恢复；重复操作的请求/响应与位置在同一事务提交，不单独清除去重记录。保存仅使用会话身份、有效正文锚点、内容版本、服务器记录版本及 UUID 操作标识，不使用客户端时间决定覆盖。账号和有效会话锁持有到提交，撤销先完成时写入被拒绝。

浏览器以 `studyloop_position:<已验证用户ID>:<资料ID>:<内容版本>` 为键暂存未同步位置与待确认操作，不包含登录凭据或整本文本。退出会清理内存和停止同步，保留同一账号再次验证后可恢复的本地候选。连续滚动约 5 秒、暂停约 1 秒发起保存；关闭/隐藏只作补充，跨设备可恢复服务器已确认的位置。存储受限、断网、失败或冲突有独立提示；首次读取失败不写默认位置，冲突必须选择后才再次尝试版本检查。原文弹层不参与知识点位置记录。真实设备、数据库并发与恢复验证记录在 Ticket #28。


收藏和手动掌握程度使用迁移 `0007_review_states`：`review_states` 每账号/知识点一行，`review_state_operations` 保存同事务的操作去重证据，两表随数据库一起备份。收藏与 `unlearned`（未学习）、`needs_review`（需复习）、`mastered`（已掌握）相互独立，只在用户明确操作时修改。PATCH 只带变更字段、预期版本与操作 UUID；不根据阅读行为推断掌握情况。

`/me/review/books/{book_id}/points` 以 `bookmarked` 或 `needs_review` 过滤，固定每页 20 项，按资料原文序号排序；计数与该页使用同一数据库快照，删除末页最后一项后返回有效页。前端入口为 `#/review?book=资料ID&list=bookmarked` 或 `list=needs_review`，列表进入正文使用显式知识点链接，优先于续读位置。列表与状态只读取当前会话账号，不建立离线状态队列；保存未知先重新读取，版本冲突要求刷新后明确重新操作。真实跨设备与数据库验收记录在 Ticket #29。
