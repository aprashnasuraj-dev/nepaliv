FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data VOICES_DIR=/app/voices OMP_NUM_THREADS=2

# ffmpeg: mp3 encode/decode; build-essential: pyworld builds from source on some platforms
# add `fluidsynth` here if you use SOUNDFONT_PATH
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsndfile1 build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && apt-get purge -y build-essential && apt-get autoremove -y

COPY . .
# bake the Nepali voices into the image (~140 MB) so cold starts don't download them
RUN python scripts/download_voices.py ne_NP-chitwan-medium ne_NP-google-medium

RUN mkdir -p /data && useradd -m -u 1000 app && chown -R app /data /app
USER app
EXPOSE 8000
# $PORT lets the same image run on Render / Railway / HF Spaces (7860)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
