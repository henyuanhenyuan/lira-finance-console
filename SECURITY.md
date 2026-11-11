# 安全策略

## 报告漏洞

请通过仓库 **Security → Report a vulnerability** 私下提交，不要开公开 issue。
收到后会尽快确认，并在修复完成后与你协商披露时间。

## 部署注意

- 首次启动会自动创建演示管理员 `admin@lira.local`，上线前请立即修改密码。
- `.env` 已被忽略；`LIRA_JWT_SECRET`、`LIRA_LLM_API_KEY` 与数据库口令只通过环境变量注入，
  `LIRA_JWT_SECRET` 必须替换掉示例值。
- 接入模块的 HTTP 拉取只应指向可信来源，避免把内网地址配置进来。
- 生产环境请置于 HTTPS 之后，并限制 `ops` schema 的数据库访问权限。
