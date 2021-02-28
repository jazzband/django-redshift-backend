# -*- coding: utf-8 -*-

import unittest

from django.db import connections
from django.db.utils import NotSupportedError
from django.core.management.color import no_style


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
    "created_at" timestamp with time zone NOT NULL,
    "fk_id" integer NOT NULL
) DISTKEY("fk_id") SORTKEY("created_at", "id")
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

expected_aggregate_filter_emulated = norm_sql(
    u'''SELECT
    "testapp_testparentmodel"."id",
    "testapp_testparentmodel"."age",
    COUNT(
        CASE WHEN "testapp_testparentmodel"."age" < %s
        THEN "testapp_testchildmodel"."id" ELSE NULL END
    ) AS "cnt"
    FROM "testapp_testparentmodel"
    LEFT OUTER JOIN "testapp_testchildmodel"
    ON ("testapp_testparentmodel"."id" = "testapp_testchildmodel"."parent_id")
    GROUP BY
    "testapp_testparentmodel"."id",
    "testapp_testparentmodel"."age"
''')

expected_dml_distinct = norm_sql(
    u'''SELECT DISTINCT
    "testapp_testmodel"."id",
    "testapp_testmodel"."ctime",
    "testapp_testmodel"."text",
    "testapp_testmodel"."uuid"
    FROM "testapp_testmodel"
''')


class ModelTest(unittest.TestCase):

    def check_model_creation(self, model, expected_ddl):
        conn = connections['default']
        statements, params = conn.creation.sql_create_model(model, no_style(), set())
        sql = norm_sql(''.join(statements))
        self.assertEqual(sql, expected_ddl)

    def test_annotate(self):
        from django.db.models import Count
        from testapp.models import TestParentModel
        query = TestParentModel.objects.annotate(cnt=Count('testchildmodel')).query
        compiler = query.get_compiler(using='default')
        sql = norm_sql(compiler.as_sql()[0])
        self.assertEqual(sql, expected_dml_annotate)

    def test_emulate_aggregate_filter(self):
        self.maxDiff = None
        from django.db.models import Count, Q
        from testapp.models import TestParentModel
        query = TestParentModel.objects.annotate(
            cnt=Count('testchildmodel', filter=Q(age__lt=10))
        ).query
        compiler = query.get_compiler(using='default')
        sql = norm_sql(compiler.as_sql()[0])
        self.assertEqual(sql, expected_aggregate_filter_emulated)

    def test_insert_uuid_field(self):
        import uuid
        from django.db.models import sql
        from testapp.models import TestModel
        obj = TestModel(uuid=uuid.uuid4())
        q = sql.InsertQuery(obj)
        q.insert_values(obj._meta.local_fields, [obj])
        statements = q.get_compiler('default').as_sql()
        # uuid is the last field of TestModel
        uuid_insert_value = statements[0][1][-1]
        # the Python value for insertion must be a string whose length is 32
        self.assertEqual(type(uuid_insert_value), str)
        self.assertEqual(len(uuid_insert_value), 32)

    def test_distinct(self):
        from testapp.models import TestModel
        query = TestModel.objects.distinct().query
        compiler = query.get_compiler(using='default')
        sql = norm_sql(compiler.as_sql()[0])
        self.assertEqual(sql, expected_dml_distinct)

    def test_distinct_with_fields(self):
        from testapp.models import TestModel
        query = TestModel.objects.distinct('text').query
        compiler = query.get_compiler(using='default')
        with self.assertRaises(NotSupportedError):
            compiler.as_sql()


class MigrationTest(unittest.TestCase):

    def check_model_creation(self, model, expected_ddl):
        conn = connections['default']
        schema_editor = conn.schema_editor(collect_sql=True)
        schema_editor.deferred_sql = []
        schema_editor.create_model(model)
        sql = norm_sql(''.join(schema_editor.collected_sql))
        self.assertEqual(sql, expected_ddl)

    def test_create_model(self):
        from testapp.models import TestModel
        self.check_model_creation(TestModel, expected_ddl_normal)

    def test_create_table_meta_keys(self):
        from testapp.models import TestModelWithMetaKeys
        self.check_model_creation(TestModelWithMetaKeys, expected_ddl_meta_keys)
