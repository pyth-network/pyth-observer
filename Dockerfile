FROM python:3.8

ADD . /data

WORKDIR /data

RUN cd pyth-client-py && \
    python setup.py install && \
    cd .. && \
    rm -rf pyth-client-py && \
    git clean -fdx && \
    pip install -r requirements.txt

ENTRYPOINT ["python3", "/data/observer.py"]
CMD ["-l", "debug", "--network", "devnet"]
