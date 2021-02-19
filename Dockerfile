FROM python:3.8

LABEL maintainer="Nadja Rhodes"

COPY ./ /app/

RUN pip install -e /app
