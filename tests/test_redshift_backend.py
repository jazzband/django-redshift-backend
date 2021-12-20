# -*- coding: utf-8 -*-

import unittest
from unittest import mock

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

expected_table_description_metadata = norm_sql(
    u'''SELECT
        a.attname AS column_name,
        NOT (a.attnotnull OR (t.typtype = 'd' AND t.typnotnull)) AS is_nullable,
        pg_get_expr(ad.adbin, ad.adrelid) AS column_default
    FROM pg_attribute a
    LEFT JOIN pg_attrdef ad ON a.attrelid = ad.adrelid AND a.attnum = ad.adnum
    JOIN pg_type t ON a.atttypid = t.oid
    JOIN pg_class c ON a.attrelid = c.oid
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE c.relkind IN ('f', 'm', 'p', 'r', 'v')
        AND c.relname = %s
        AND n.nspname NOT IN ('pg_catalog', 'pg_toast')
        AND pg_catalog.pg_table_is_visible(c.oid)
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


class IntrospectionTest(unittest.TestCase):

    def test_get_table_description_does_not_use_collations(self):
        conn = connections['default']
        with mock.patch.object(conn, 'cursor') as mock_cursor_method:
            mock_cursor = mock_cursor_method.return_value.__enter__.return_value
            from testapp.models import TestModel
            table_name = TestModel._meta.db_table

            _table_description = conn.introspection.get_table_description(mock_cursor, table_name)

            (select_metadata_call, fetchall_call, select_row_call) = mock_cursor.method_calls

            self.assertEqual('execute', select_metadata_call[0])
            executed_sql = norm_sql(select_metadata_call.args[0])

            self.assertEqual(expected_table_description_metadata, executed_sql)
            self.assertNotIn('collation', executed_sql)

            self.assertEqual(
                norm_sql('SELECT * FROM "testapp_testmodel" LIMIT 1'),
                select_row_call.args[0],
            )
