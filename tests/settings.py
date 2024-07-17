# -*- coding: utf-8 -*-
import os
import environ

if uri := os.environ.get("TEST_WITH_REDSHIFT"):
    # use URI if it has least one charactor.
    os.environ["DATABASE_URL"] = uri
else:
    os.environ["DATABASE_URL"] = "redshift://user:password@localhost:5439/testing"
env = environ.Env()

DATABASES = {
    'default': env.db()
}

SECRET_KEY = '<key>'
