FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application source code
COPY . .

# Expose web port
EXPOSE 5000

ENV PYTHONUNBUFFERED=1
ENV PORT=5000
ENV REDIS_HOST=redis
ENV REDIS_PORT=6379

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

CMD ["python", "-u", "app.py"]
