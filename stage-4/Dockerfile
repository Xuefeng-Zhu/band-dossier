FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DOSSIER_STATE_FILE=/data/dossier.sqlite3
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && install -d -m 0700 -o 10001 -g 10001 /data
COPY candidates.py evidence.py research.py service.py store.py temporal.py index.html ui.css ui.js ./

USER 10001:10001
EXPOSE 8080
CMD ["python", "service.py"]
