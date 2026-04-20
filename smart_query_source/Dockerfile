FROM python:3.11-slim

# Keep Python output unbuffered and avoid writing .pyc files
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first to leverage Docker layer caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app

ENV PORT=${PORT:-8010}

EXPOSE $PORT

# Run the FastAPI app
CMD ["uvicorn", "src.fastapi_app:app", "--host", "0.0.0.0", "--port", "$PORT"]
