# syntax=docker/dockerfile:1.2

FROM python:3.8-slim-bullseye

RUN addgroup --system app && adduser --system --group app
COPY . /data
WORKDIR /data
RUN pip install --no-cache-dir -r requirements.txt && \
  chown -R app:app /data
USER app

ENTRYPOINT ["python3", "/data/observer.py"]
CMD ["-l", "debug", "--network", "devnet"]
