# Report Service Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for WeasyPrint (optional PDF generation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY report-svc/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# Copy application code
COPY report-svc/ .

# Copy shared modules
COPY shared/ ./shared/

# Set PYTHONPATH to include the current directory so 'app' and 'shared' can be found
ENV PYTHONPATH=/app

# Create directories
RUN mkdir -p /tmp/device-farm/reports

# Expose port
EXPOSE 8002

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
