# Multi-stage build for production-ready Python file connector
FROM python:3.11-slim as builder

# Set build arguments
ARG BUILD_ENV=production
ARG PYTHONUNBUFFERED=1

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies required for building
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src/ ./src/
COPY config/ ./config/
COPY *.py ./

# Production stage
FROM python:3.11-slim as production

# Set production environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONNECTOR_ENVIRONMENT=production \
    CONNECTOR_LOG_LEVEL=INFO

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r connector \
    && useradd -r -g connector connector

# Create application directory and set permissions
WORKDIR /app
RUN chown -R connector:connector /app

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application files
COPY --from=builder --chown=connector:connector /app .

# Create directories for logs and data
RUN mkdir -p /app/logs /app/data /app/credentials \
    && chown -R connector:connector /app/logs /app/data /app/credentials

# Switch to non-root user
USER connector

# Expose health check port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# Default command
CMD ["python", "-m", "src.connector.main"]


# Development stage
FROM python:3.11-slim as development

# Set development environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONNECTOR_ENVIRONMENT=development \
    CONNECTOR_LOG_LEVEL=DEBUG

# Install development dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    git \
    curl \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install development dependencies
RUN pip install --no-cache-dir \
    pytest \
    pytest-asyncio \
    pytest-mock \
    pytest-cov \
    black \
    flake8 \
    mypy \
    ipython

# Copy application source
COPY . .

# Create directories
RUN mkdir -p /app/logs /app/data /app/credentials

# Expose ports for development
EXPOSE 8080 5678

# Development command with auto-reload
CMD ["python", "-m", "src.connector.main", "--dev"]


# Testing stage
FROM development as testing

# Install additional testing dependencies
RUN pip install --no-cache-dir \
    coverage \
    pytest-html \
    pytest-xdist

# Copy test files
COPY tests/ ./tests/

# Run tests as default command
CMD ["python", "-m", "pytest", "tests/", "-v", "--cov=src/connector", "--cov-report=html"]