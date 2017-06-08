FROM python:3.6.1

RUN pip install -U setuptools pip

COPY . /app
WORKDIR /app
VOLUME /app

RUN pip install -U -r test-requires.txt tox

CMD ["tox", "-e", "flake8,py{27,36}-django{18,19,110,111}"]

