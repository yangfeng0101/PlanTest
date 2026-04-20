FROM python:3.11-slim

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY ai-svc/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# Copy shared modules
COPY shared/ ./shared/

# Copy application
COPY ai-svc/app/ ./app/

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8005

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
