FROM python:3.12-slim

WORKDIR /app

# Non-root user — UID 1000 matches typical host UIDs so volume files
# are readable without chown gymnastics.
RUN useradd -r -u 1000 -g root licserver

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/     ./app/
COPY scripts/ ./scripts/

# /data is the volume mount point for the SQLite database.
RUN mkdir -p /data && chown licserver /data

USER licserver

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
