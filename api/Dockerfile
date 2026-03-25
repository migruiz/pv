FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install uv via pip (avoids GHCR dependency)
RUN pip install --no-cache-dir uv

WORKDIR /app

# Non-root user
RUN groupadd --gid 1000 app \
 && useradd  --uid 1000 --gid app --shell /bin/sh --create-home app

# Persistent data directory for cookies
RUN mkdir -p /data && chown app:app /data

# --- Dependency layer (cached unless pyproject.toml/uv.lock change) ---
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# --- Application layer ---
COPY main.py auth.py session.py ./
RUN uv sync --frozen --no-dev

# Symlink cookies to persistent volume so session.py's
# Path(__file__).parent / "cookies.json" writes to /data
RUN ln -sf /data/cookies.json /app/cookies.json

USER app

VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
