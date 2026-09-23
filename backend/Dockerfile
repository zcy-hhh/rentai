FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy

# 依赖层（利用层缓存）
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev

# 应用代码
COPY app ./app
COPY evals ./evals

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
