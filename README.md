# StudyLoop

通用 AI 在线复习平台。已提供中文首页、邮箱注册/验证/重发、登录与退出、只读个人中心、复习占位页、平台连接状态和 HTTPS API；资料编辑、头像及 AI 复习由后续切片实现。

前端目标：<https://njuywy.github.io/StudyLoop/>。后端目标：`https://124.220.147.193/api/v1`。这些是部署目标，仓库有代码不代表线上已部署或验收通过。

## 本地开发

需要 Node.js 22.12+、Python 3.12+ 和 uv 0.12.22。安装依赖不会启动 PostgreSQL 或 Docker。

```bash
npm ci --prefix frontend
uv sync --project backend --frozen
cp backend/.env.example backend/.env
```

将 `backend/.env` 的 `DATABASE_URL` 设置为已有 PostgreSQL 的连接，开发 CORS 来源已列在示例中。注册发信还需要配置后端 SMTP（详见[运行指南](docs/operations.md#邮件服务与注册)）；未配置时注册保留待验证账号并返回发送失败。两个终端分别运行：

```bash
npm run dev --prefix frontend
uv run --project backend uvicorn studyloop.main:app --app-dir backend/src --env-file backend/.env --host 127.0.0.1 --port 8000 --reload
```

前端开发配置复制 `frontend/.env.example` 为 `frontend/.env.local`，本地可使用 `VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1`。生产构建要求 HTTPS；构建线上版本前移除本地覆盖，或将其改为目标 HTTPS 地址。浏览器只能获得公开的 API 地址，数据库与 SMTP 凭据仅配置在后端。

## 检查

```bash
npm run build --prefix frontend
npm exec --prefix frontend -- playwright install chromium
npm run test:e2e --prefix frontend
uv run --project backend ruff check backend
uv run --project backend ruff format --check backend
uv run --project backend pytest backend/tests -q
```

HTTP 测试证明状态码、错误脱敏和 CORS；浏览器测试验证 `/StudyLoop/` 子路径、hash 刷新、故障提示与重试，并拦截健康请求。它们不证明实际 PostgreSQL、可信证书或公网部署可用。

真实数据库入口：由操作者提供**已经运行的隔离测试数据库**，配置 `TEST_DATABASE_URL` 后执行：

```bash
uv run --project backend pytest backend/tests -m postgres -q
```

数据库用例会迁移该数据库，不可提供生产连接。未配置时明确跳过，不启动验证服务。CI 同样只在 `STUDYLOOP_TEST_DATABASE_URL` Secret 已配置时连接已有测试数据库，其余情况记录未执行。

## 迁移与发布

```bash
uv run --project backend python -m dotenv -f backend/.env run -- alembic -c backend/alembic.ini upgrade head
```

`0001_baseline` 建立迁移历史，`0002_registration` 建立账号、邮箱令牌与共享入口限流表；`0003_sessions` 建立服务端可撤销会话与账号禁用撤销规则。迁移重复运行应保持当前版本，数据与服务生命周期分离。

[服务器运行指南](docs/operations.md) 是部署、HTTPS 续期、配置、持久化与公网隔离核验的权威入口。使用原生 PostgreSQL、systemd 和 Nginx，不依赖 Docker。

GitHub Actions 的 `frontend`、`backend` 检查运行于 PR 和 `main` 推送；`pages` 只在 `main` 的检查成功后发布已检查的前端产物。上线时必须启用仓库 Pages 的 GitHub Actions 来源，并完成服务器端部署。

范围与验收依据：[Spec #1](https://github.com/njuywy/StudyLoop/issues/1)、[Ticket #2](https://github.com/njuywy/StudyLoop/issues/2)、[Ticket #3](https://github.com/njuywy/StudyLoop/issues/3)、[Ticket #4](https://github.com/njuywy/StudyLoop/issues/4)。测试执行状态和人工验收结果保留在 Ticket 正文，不在仓库维护重复报告。
