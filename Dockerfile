# syntax=docker/dockerfile:1.2
FROM python:3.8-slim-bullseye

ARG UID=10000
ARG GID=10000
ARG DIR=/data

WORKDIR ${DIR}
RUN groupadd -o -g ${GID} -r app && adduser --system --home ${DIR} --ingroup app --uid ${UID} app

COPY --chown=app:app . ${DIR}
RUN pip install --no-cache-dir -r requirements.txt
USER app

ENTRYPOINT ["python3", "/data/observer.py"]
CMD ["-l", "debug", "--network", "devnet"]
