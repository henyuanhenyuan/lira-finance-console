# 参与贡献

## 本地运行

```bash
docker compose up -d
```

```bash
cd backend && uv venv .venv --python 3.12 && uv pip install --python .venv/Scripts/python.exe -e .
```

```bash
cd frontend && npm install && npm run build
```

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8012
```

打开 <http://localhost:8012>。Windows 下也可以用 `.\start.ps1` 一键完成。

## 提交前自检

与 CI 保持一致：

```bash
python -m compileall -q backend/app
npm run build --prefix frontend
```

## 提 PR

- 一个 PR 只做一件事，说明改动动机与验证方式。
- 指标口径改动必须落在 `backend/app/metrics.py`，不要在别处复制计算逻辑；数字只来自 SQL。
- 新增 Agent 或工具时同步补 `agent` / `eval` 侧的用例与说明。
- 改动接口或页面时同步更新 `README.md` 与 `ARCHITECTURE.md`。

## 提交信息

采用 `feat:` / `fix:` / `docs:` / `chore:` 前缀，正文说明「为什么」而非「做了什么」。
