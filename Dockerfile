FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# Dependencies get their own layer: as long as pyproject.toml/uv.lock don't
# change, Docker reuses this RUN's cache instead of reinstalling on every
# edit to src/.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "python", "-m", "support_platform.main"]
