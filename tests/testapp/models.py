# -*- coding: utf-8 -*-

from django.db.models import Model
from django.db.models import AutoField, DateTimeField, TextField


class TestModel(Model):
    ctime = DateTimeField()
    text = TextField()
