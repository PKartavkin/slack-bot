FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy main app and source folder
COPY app.py .
COPY src/ ./src/

# Run the app with uvicorn (FastAPI)
CMD ["uvicorn", "app:fastapi_app", "--host", "0.0.0.0", "--port", "3000"]
