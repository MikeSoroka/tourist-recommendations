FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps -e .

COPY . .

RUN useradd --create-home --uid 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "run:app"]

FROM runtime AS tools

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential libopenmpi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-analysis.txt .
RUN pip install --no-cache-dir -r requirements-analysis.txt

USER appuser
