# Hedging Grid Robot - Production Docker Image
# Multi-stage build for minimal image size

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Builder
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Production
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim as production

# Labels
LABEL maintainer="Aliasqar Islomov"
LABEL description="Hedging Grid Robot - Grid Hedging Trading Bot for HEMA"
LABEL version="1.0.0"

# Create non-root user
RUN useradd --create-home --shell /bin/bash hedgingbot

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=hedgingbot:hedgingbot hedging_robot/ ./hedging_robot/
COPY --chown=hedgingbot:hedgingbot run.py run_server.py ./

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BOT_ID=hedging-grid-bot \
    BOT_NAME="Hedging Grid Robot" \
    BOT_VERSION=1.0.0 \
    SERVER_PORT=8082

# Switch to non-root user
USER hedgingbot

# Expose port
EXPOSE 8082

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8082/health')" || exit 1

# Default command (server mode)
CMD ["python", "run_server.py"]
