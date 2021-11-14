# syntax=docker/dockerfile:1.2

FROM docker.io/pythfoundation/pyth-client-py:v0.0.1

COPY . /data

WORKDIR /data

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["python3", "/data/observer.py"]
CMD ["-l", "debug", "--network", "devnet"]
