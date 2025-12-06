# Dockerfile for Admin Panel service
FROM python:3.11-slim

# Disable Python output buffering for real-time logs
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY admin-panel/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot folder (needed for database connection)
COPY bot/ ./bot/

# Copy admin-panel folder
COPY admin-panel/ ./admin-panel/

# Run the app with uvicorn (FastAPI)
CMD ["uvicorn", "admin-panel.app:app", "--host", "0.0.0.0", "--port", "3001", "--log-level", "info", "--access-log"]
