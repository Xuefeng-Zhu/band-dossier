FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY candidates.py evidence.py research.py service.py index.html ui.css ui.js ./

USER 10001:10001
EXPOSE 8080
CMD ["python", "service.py"]
