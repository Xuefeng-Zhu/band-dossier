FROM python:3.12-slim
WORKDIR /srv/dossier
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8080
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py state.py evidence.py research.py ./
USER 65534:65534
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port \"$PORT\" --no-access-log"]
