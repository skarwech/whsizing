# §3.3. Pango + fonts for WeasyPrint (the Debian list of its docs, libharfbuzz-subset0 included);
# deps installed from uv.lock before the source for caching. The Streamlit demo runs from the same
# image: docker run -p 8501:8501 --entrypoint streamlit whsizing:dev run streamlit_app.py
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fonts-dejavu fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev
EXPOSE 8501
ENTRYPOINT ["whsizing"]
