# -*- coding: utf-8 -*-

from django.db import models


class TestModel(models.Model):
    ctime = models.DateTimeField()
    text = models.TextField()
    uuid = models.UUIDField()


class TestModelWithMetaKeys(models.Model):
    name = models.CharField(max_length=100)
    age = models.IntegerField()
    created_at = models.DateTimeField()

    class Meta:
        ordering = ['created_at', '-id']


class TestParentModel(models.Model):
    age = models.IntegerField()


class TestChildModel(models.Model):
    parent = models.ForeignKey(TestParentModel)
    age = models.IntegerField()
