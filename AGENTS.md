# StudyLoop 工程入口

- 前端位于 `frontend/`，Vue 3 / TypeScript / Vite，Pages 基础路径为 `/StudyLoop/`，使用 hash 路由。
- 后端位于 `backend/src/studyloop/`，FastAPI；API 前缀 `/api/v1`，数据库为 PostgreSQL，迁移位于 `backend/migrations/`。
- [README](README.md) 是本地依赖、启动、验证和迁移命令的入口；[运行指南](docs/operations.md) 是 systemd、Nginx、HTTPS、持久化与服务器配置的权威入口。
- 前端构建只注入公开 API 地址；数据库和 SMTP 凭据留在后端私有配置，不能提交或记录至日志。
- PostgreSQL 集成测试仅连接操作者提供的已有隔离 `TEST_DATABASE_URL`，会迁移并创建/清理验证数据，不得使用生产数据库；缺少连接时跳过，不表示已验证数据库。
- 前端检查：`npm run build --prefix frontend`、`npm run test:e2e --prefix frontend`；后端检查：`uv run --project backend ruff check backend`、`uv run --project backend ruff format --check backend`、`uv run --project backend pytest backend/tests -q`。
- 需求和验收使用 GitHub Issues；首期账号 Spec #1，工作台与视觉优化 Spec #18；按各 Ticket 的原生 parent 和正文核对来源，各 Ticket 保留其权威测试用例与人工验收状态。
- 本项目的自动选取 Ticket 与合并授权见[交付授权](docs/agents/delivery-policy.md)，实施前一并读取。
