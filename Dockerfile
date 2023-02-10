FROM python:3.10-slim-bullseye

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN apt-get update -y
RUN apt-get install -y fonts-dejavu-core

COPY julia_mem_api.py .

CMD uvicorn julia_mem_api:app --host 0.0.0.0 --port 8080


# deploy to Fly.io
# https://dev.to/denvercoder1/hosting-a-python-discord-bot-for-free-with-flyio-3k19