FROM python:3.11-slim

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1


# Install system dependencies required by python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    tesseract-ocr \
    espeak-ng \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Provider-name source guard. Fails the image build on a hard-coded leak.
COPY scripts/check_provider_leak.sh /tmp/check_provider_leak.sh
RUN grep -rIl '' app \
      | grep -vE 'app/core/providers.py|app/core/config.py|app/models.py|app/api/endpoints.py|app/services/connections/' \
      | xargs cat 2>/dev/null \
      | sh /tmp/check_provider_leak.sh

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
