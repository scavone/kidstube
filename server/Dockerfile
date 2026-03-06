FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN adduser --disabled-password --no-create-home --uid 1000 appuser \
    && mkdir -p /app/db \
    && chown -R appuser:appuser /app/db

EXPOSE 8080

USER appuser

CMD ["python", "main.py"]
