FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh \
    && useradd -r -s /bin/false appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["./entrypoint.sh"]
