FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ENV DOSSIER_STATE_PATH=/data/state.json
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY service.py evidence.py research.py visible.py temporal.py lineage.py budgets.py ./
COPY web ./web
RUN mkdir /data && chown nobody:nogroup /data
USER nobody
CMD ["python", "service.py"]
