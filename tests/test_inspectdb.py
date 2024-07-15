import os
from io import StringIO
from textwrap import dedent
from unittest import mock
import unittest

from django.db import connections
from django.core.management import call_command

from test_base import OperationTestBase

from conftest import skipif_no_database, postgres_fixture

def norm_sql(sql):
    return ' '.join(sql.split()).replace('( ', '(').replace(' )', ')').replace(' ;', ';')


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
            idx.indkey,  -- type "int2vector", returns space-separated string
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


@skipif_no_database
class InspectDbTests(OperationTestBase):
    available_apps = []
    databases = {'default'}

    expected_pony_model = dedent('''
        from django.db import models


        class TestPony(models.Model):
            pink = models.IntegerField()
            weight = models.FloatField()

            class Meta:
                managed = False
                db_table = 'test_pony'
    ''')

    def tearDown(self):
        self.cleanup_test_tables()

    @postgres_fixture()
    def test_inspectdb(self):
        self.set_up_test_model('test')
        out = StringIO()
        call_command('inspectdb', 'test_pony', stdout=out)
        print(out.getvalue())
        self.assertIn(self.expected_pony_model, out.getvalue())
