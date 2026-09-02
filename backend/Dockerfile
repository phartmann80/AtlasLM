FROM python:3.11-slim

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1


# Install system dependencies required by python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    tesseract-ocr \
    tesseract-ocr-eng \
    espeak-ng \
    ffmpeg \
    chromium \
    fonts-liberation \
    fonts-dejavu-core \
    fontconfig \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kokoro-82M ONNX weights for CPU TTS in the worker. No GPU.
# SHA-256 of the GitHub release assets for tag model-files-v1.0 (hashed 2026-09-02).
# sha256sum -c fails the image build on mismatch.
ARG KOKORO_MODEL_SHA256=7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5
ARG KOKORO_VOICES_SHA256=bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d
RUN mkdir -p /voices \
    && wget -q -O /voices/kokoro-v1.0.onnx \
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx \
    && wget -q -O /voices/voices-v1.0.bin \
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin \
    && echo "${KOKORO_MODEL_SHA256}  /voices/kokoro-v1.0.onnx" | sha256sum -c - \
    && echo "${KOKORO_VOICES_SHA256}  /voices/voices-v1.0.bin" | sha256sum -c -

COPY . .

# Provider-name source guard. Fails the image build on a hard-coded leak.
COPY scripts/check_provider_leak.sh /tmp/check_provider_leak.sh
RUN grep -rIl '' app \
      | grep -vE 'app/core/providers.py|app/core/config.py|app/models.py|app/api/endpoints.py|app/services/connections/' \
      | xargs cat 2>/dev/null \
      | sh /tmp/check_provider_leak.sh

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
