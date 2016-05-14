# -*- coding: utf-8 -*-

import unittest

import django
from django.db import connections
from django.core.management.color import no_style
import pytest


def norm_sql(sql):
    r = sql
    r = r.replace(' ', '')
    r = r.replace('\n', '')
    return r


class DatabaseWrapperTest(unittest.TestCase):

    def test_load_redshift_backend(self):
        db = connections['default']
        self.assertIsNotNone(db)


expected_ddl = norm_sql(
    u'''CREATE TABLE "testapp_testmodel" (
    "id" integer identity(1, 1) NOT NULL PRIMARY KEY,
    "ctime" timestamp NOT NULL,
    "text" varchar(max) NOT NULL
)
;''')


class ModelTest(unittest.TestCase):

    @pytest.mark.skipif(django.VERSION >= (1, 9),
                        reason="Django-1.9 or later doesn't support sql creation")
    def test_create_table(self):
        from testapp import models
        model = models.TestModel
        conn = connections['default']
        statements, params = conn.creation.sql_create_model(model, no_style(), set())
        sql = norm_sql(''.join(statements))
        self.assertEqual(sql, expected_ddl)


class MigrationTest(unittest.TestCase):

    @pytest.mark.skipif(django.VERSION < (1, 8),
                        reason="Django-1.8 or earlier doesn't support migration")
    def test_create_model(self):
        from testapp import models
        model = models.TestModel
        conn = connections['default']
        schema_editor = conn.schema_editor(collect_sql=True)
        schema_editor.deferred_sql = []
        schema_editor.create_model(model)
        sql = norm_sql(''.join(schema_editor.collected_sql))
        self.assertEqual(sql, expected_ddl)
