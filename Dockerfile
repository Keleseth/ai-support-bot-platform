FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# Отдельный слой на зависимости: пока pyproject.toml/uv.lock не менялись,
# Docker переиспользует кеш этого RUN и не переустанавливает зависимости
# на каждую правку кода в src/.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "python", "-m", "support_platform.main"]
