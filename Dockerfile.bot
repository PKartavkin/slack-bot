# Dockerfile for Slack Bot service
FROM python:3.11-slim

# Disable Python output buffering for real-time logs in Railway
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot folder
COPY bot/ ./bot/

# Run the app with uvicorn (FastAPI)
# --log-level info: Show INFO and above logs
# --access-log: Show HTTP access logs
CMD ["uvicorn", "bot.app:fastapi_app", "--host", "0.0.0.0", "--port", "3000", "--log-level", "info", "--access-log"]
