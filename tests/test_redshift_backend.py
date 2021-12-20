# -*- coding: utf-8 -*-

import unittest
from unittest import mock

from django.db import connections
from django.db.utils import NotSupportedError
from django.core.management.color import no_style


def norm_sql(sql):
    return ' '.join(sql.split()).replace('( ', '(').replace(' )', ')').replace(' ;', ';')


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


class IntrospectionTest(unittest.TestCase):
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

    expected_constraints_query = norm_sql(
        u''' SELECT
            c.conname,
            c.conkey::int[],
            c.conrelid,
            c.contype,
            (SELECT fkc.relname || '.' || fka.attname
            FROM pg_attribute AS fka
            JOIN pg_class AS fkc ON fka.attrelid = fkc.oid
            WHERE fka.attrelid = c.confrelid AND fka.attnum = c.confkey[1])
        FROM pg_constraint AS c
        JOIN pg_class AS cl ON c.conrelid = cl.oid
        WHERE cl.relname = %s AND pg_catalog.pg_table_is_visible(cl.oid)
    ''')

    expected_attributes_query = norm_sql(
        u'''SELECT
            attrelid, -- table oid
            attnum,
            attname
        FROM pg_attribute
        WHERE pg_attribute.attrelid = %s
        ORDER BY attrelid, attnum;
    ''')

    expected_indexes_query = norm_sql(
        u'''SELECT
            c2.relname,
            idx.indrelid,
            idx.indkey,
            -- indkey is of type "int2vector" and returns a space-separated string
            idx.indisunique,
            idx.indisprimary
        FROM
            pg_catalog.pg_class c,
            pg_catalog.pg_class c2,
            pg_catalog.pg_index idx
        WHERE
            c.oid = idx.indrelid
            AND idx.indexrelid = c2.oid
            AND c.relname = %s
    ''')

    def test_get_table_description_does_not_use_unsupported_functions(self):
        conn = connections['default']
        with mock.patch.object(conn, 'cursor') as mock_cursor_method:
            mock_cursor = mock_cursor_method.return_value.__enter__.return_value
            from testapp.models import TestModel
            table_name = TestModel._meta.db_table

            _ = conn.introspection.get_table_description(mock_cursor, table_name)

            (
                select_metadata_call,
                fetchall_call,
                select_row_call
            ) = mock_cursor.method_calls

            call_method, call_args, call_kwargs = select_metadata_call
            self.assertEqual('execute', call_method)
            executed_sql = norm_sql(call_args[0])

            self.assertEqual(self.expected_table_description_metadata, executed_sql)

            self.assertNotIn('collation', executed_sql)
            self.assertNotIn('unnest', executed_sql)

            call_method, call_args, call_kwargs = select_row_call
            self.assertEqual(
                norm_sql('SELECT * FROM "testapp_testmodel" LIMIT 1'),
                call_args[0],
            )

    def test_get_get_constraints_does_not_use_unsupported_functions(self):
        conn = connections['default']
        with mock.patch.object(conn, 'cursor') as mock_cursor_method:
            mock_cursor = mock_cursor_method.return_value.__enter__.return_value
            from testapp.models import TestModel
            table_name = TestModel._meta.db_table

            mock_cursor.fetchall.side_effect = [
                # conname, conkey, conrelid, contype, used_cols)
                [
                    (
                        'testapp_testmodel_testapp_testmodel_id_pkey',
                        [1],
                        12345678,
                        'p',
                        None,
                    ),
                ],
                [
                    # attrelid, attnum, attname
                    (12345678, 1, 'id'),
                    (12345678, 2, 'ctime'),
                    (12345678, 3, 'text'),
                    (12345678, 4, 'uuid'),
                ],
                # index_name, indrelid, indkey, unique, primary
                [
                    (
                        'testapp_testmodel_testapp_testmodel_id_pkey',
                        12345678,
                        '1',
                        True,
                        True,
                    ),
                ],
            ]

            table_constraints = conn.introspection.get_constraints(
                mock_cursor, table_name)

            expected_table_constraints = {
                'testapp_testmodel_testapp_testmodel_id_pkey': {
                    'columns': ['id'],
                    'primary_key': True,
                    'unique': True,
                    'foreign_key': None,
                    'check': False,
                    'index': False,
                    'definition': None,
                    'options': None,
                }
            }
            self.assertDictEqual(expected_table_constraints, table_constraints)

            calls = mock_cursor.method_calls

            # Should be a sequence of 3x execute and fetchall calls
            expected_call_sequence = ['execute', 'fetchall'] * 3
            actual_call_sequence = [name for (name, _args, _kwargs) in calls]
            self.assertEqual(expected_call_sequence, actual_call_sequence)

            # Constraints query
            call_method, call_args, call_kwargs = calls[0]
            executed_sql = norm_sql(call_args[0])
            self.assertNotIn('collation', executed_sql)
            self.assertNotIn('unnest', executed_sql)
            self.assertEqual(self.expected_constraints_query, executed_sql)

            # Attributes query
            call_method, call_args, call_kwargs = calls[2]
            executed_sql = norm_sql(call_args[0])
            self.assertNotIn('collation', executed_sql)
            self.assertNotIn('unnest', executed_sql)
            self.assertEqual(self.expected_attributes_query, executed_sql)

            # Indexes query
            call_method, call_args, call_kwargs = calls[4]
            executed_sql = norm_sql(call_args[0])
            self.assertNotIn('collation', executed_sql)
            self.assertNotIn('unnest', executed_sql)
            self.assertEqual(self.expected_indexes_query, executed_sql)
