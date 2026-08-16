FROM python:3.13-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY generate_config.py /app/generate_config.py

CMD ["python", "/app/generate_config.py"]
