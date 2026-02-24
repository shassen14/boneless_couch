FROM python:3.13-slim

WORKDIR /app

COPY requirements.in .
RUN pip install --no-cache-dir -r requirements.in

COPY . .
RUN echo "/app/.env" > .env.path
