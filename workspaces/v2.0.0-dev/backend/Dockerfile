FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for OpenCV and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency requirements
COPY requirements-host.txt requirements.txt

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application source
COPY . .

# Expose FastAPI port
EXPOSE 4000

# Default command runs FastAPI host server with central database initialization
CMD ["sh", "-c", "python -m scripts.init_central_db || true && uvicorn app.main:app --host 0.0.0.0 --port 4000"]
