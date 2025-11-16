FROM python:3.12-alpine AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# let Docker weten dat het bestand in core-api/ staat
COPY core-api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY core-api/app ./app
COPY schemas ./schemas

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
