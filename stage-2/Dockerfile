FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY service.py evidence.py research.py visible.py ./
COPY web ./web
USER nobody
CMD ["python", "service.py"]
