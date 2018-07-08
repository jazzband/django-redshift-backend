# -*- coding: utf-8 -*-

from django.db import models

from django_redshift_backend.base import DistKey


class TestModel(models.Model):
    ctime = models.DateTimeField()
    text = models.TextField()
    uuid = models.UUIDField()


class TestReferencedModel(models.Model):
    id = models.IntegerField()


class TestModelWithMetaKeys(models.Model):
    name = models.CharField(max_length=100)
    age = models.IntegerField()
    created_at = models.DateTimeField()
    fk = models.ForeignKey(TestReferencedModel, on_delete=models.CASCADE)

    class Meta:
        indexes = [DistKey(fields=['fk'])]
        ordering = ['created_at', '-id']


class TestParentModel(models.Model):
    age = models.IntegerField()


class TestChildModel(models.Model):
    parent = models.ForeignKey(TestParentModel, on_delete=models.CASCADE)
    age = models.IntegerField()
