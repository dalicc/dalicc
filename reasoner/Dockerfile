FROM tiangolo/uvicorn-gunicorn:python3.7

#LABEL maintainer="Sebastian Ramirez <tiangolo@gmail.com>"

RUN pip install --no-cache-dir fastapi


WORKDIR /app

COPY /requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

