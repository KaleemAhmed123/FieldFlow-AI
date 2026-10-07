# Orchestrator image (optional for the spine — `make dev` runs it on the host).
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY . /src
RUN uv pip install --system /src/packages/contract /src/apps/orchestrator
WORKDIR /src/apps/orchestrator
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
