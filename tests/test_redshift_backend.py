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


expected_ddl_normal = norm_sql(
    u'''CREATE TABLE "testapp_testmodel" (
    "id" integer identity(1, 1) NOT NULL PRIMARY KEY,
    "ctime" timestamp with time zone NOT NULL,
    "text" varchar(max) NOT NULL,
    "uuid" varchar(32) NOT NULL
)
;''')

expected_ddl_meta_keys = norm_sql(
    u'''CREATE TABLE "testapp_testmodelwithmetakeys" (
    "id" integer identity(1, 1) NOT NULL PRIMARY KEY,
    "name" varchar(100) NOT NULL,
    "age" integer NOT NULL,
    "created_at" timestamp with time zone NOT NULL
) SORTKEY("created_at", "id")
;''')


expected_dml_annotate = norm_sql(
    u'''SELECT
    "testapp_testparentmodel"."id",
    "testapp_testparentmodel"."age",
    COUNT("testapp_testchildmodel"."id") AS "cnt"
    FROM "testapp_testparentmodel"
    LEFT OUTER JOIN "testapp_testchildmodel"
    ON ("testapp_testparentmodel"."id" = "testapp_testchildmodel"."parent_id")
    GROUP BY
    "testapp_testparentmodel"."id",
    "testapp_testparentmodel"."age"
''')


class ModelTest(unittest.TestCase):

    def check_model_creation(self, model, expected_ddl):
        conn = connections['default']
        statements, params = conn.creation.sql_create_model(model, no_style(), set())
        sql = norm_sql(''.join(statements))
        self.assertEqual(sql, expected_ddl)

    @pytest.mark.skipif(django.VERSION >= (1, 9),
                        reason="Django-1.9 or later doesn't support sql creation")
    def test_create_table(self):
        from testapp.models import TestModel
        self.check_model_creation(TestModel, expected_ddl_normal)

    def test_annotate(self):
        from django.db.models import Count
        from testapp.models import TestParentModel
        query = TestParentModel.objects.annotate(cnt=Count('testchildmodel')).query
        compiler = query.get_compiler(using='default')
        sql = norm_sql(compiler.as_sql()[0])
        self.assertEqual(sql, expected_dml_annotate)


class MigrationTest(unittest.TestCase):

    def check_model_creation(self, model, expected_ddl):
        conn = connections['default']
        schema_editor = conn.schema_editor(collect_sql=True)
        schema_editor.deferred_sql = []
        schema_editor.create_model(model)
        sql = norm_sql(''.join(schema_editor.collected_sql))
        self.assertEqual(sql, expected_ddl)

    @pytest.mark.skipif(django.VERSION < (1, 8),
                        reason="Django-1.8 or earlier doesn't support migration")
    def test_create_model(self):
        from testapp.models import TestModel
        self.check_model_creation(TestModel, expected_ddl_normal)

    @pytest.mark.skipif(django.VERSION < (1, 8),
                        reason="Django-1.8 or earlier doesn't support migration")
    def test_create_table_meta_keys(self):
        from testapp.models import TestModelWithMetaKeys
        self.check_model_creation(TestModelWithMetaKeys, expected_ddl_meta_keys)
