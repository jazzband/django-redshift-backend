FROM python:3.5.2

RUN pip install -U setuptools pip

COPY . /app
WORKDIR /app
VOLUME /app

RUN pip install -U -r test-requires.txt tox

CMD ["tox", "-e", "flake8,py{27,35}-django{17,18,19,110,111}"]

