import os
from unittest import mock

from django.db import connection, migrations, models
import pytest

from django_redshift_backend.base import BasePGDatabaseWrapper
from test_base import OperationTestBase


@pytest.mark.skipif(not os.environ.get('TEST_WITH_POSTGRES'),
                    reason='to run, TEST_WITH_POSTGRES=1 tox')
class MigrationTests(OperationTestBase):
    available_apps = ["testapp"]
    databases = {'default'}

    def tearDown(self):
        self.cleanup_test_tables()
        # super().tearDown()  # disabled: DELETE from django_migrations

    @mock.patch('django_redshift_backend.base.DatabaseWrapper.data_types', BasePGDatabaseWrapper.data_types)
    @mock.patch('django_redshift_backend.base.DatabaseSchemaEditor._get_create_options', lambda self, model: '')
    def test_alter_size(self):
        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AddField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=10, verbose_name='name', default=''),
            ),
            migrations.AlterField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=20, verbose_name='name'),
            ),
            migrations.AlterField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=10, verbose_name='name'),
            ),
        ]
        sqls = self.apply_operations_and_collect_sql('test', new_state, operations)
        print('\n'.join(sqls))
        sqls = [s for s in sqls if not s.startswith('--')]
        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "name" varchar(10) DEFAULT '' NOT NULL;''',
            '''ALTER TABLE "test_pony" ALTER COLUMN "name" TYPE varchar(20);''',
            '''ALTER TABLE "test_pony" ALTER COLUMN "name" TYPE varchar(10);''',
        ], sqls)

    @mock.patch('django_redshift_backend.base.DatabaseWrapper.data_types', BasePGDatabaseWrapper.data_types)
    @mock.patch('django_redshift_backend.base.DatabaseSchemaEditor._get_create_options', lambda self, model: '')
    # def test_add_notnull_without_default_change_to_nullable(self):
    def test_add_notnull_without_default_raise_exception(self):
        from django.db.utils import ProgrammingError
        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AddField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=10, verbose_name='name', null=False),
            ),
        ]
        with self.assertRaises(ProgrammingError):
            sqls = self.apply_operations_and_collect_sql('test', new_state, operations)
            print(sqls)  # for debug

    @mock.patch('django_redshift_backend.base.DatabaseWrapper.data_types', BasePGDatabaseWrapper.data_types)
    @mock.patch('django_redshift_backend.base.DatabaseSchemaEditor._get_create_options', lambda self, model: '')
    def test_add_notnull_with_default(self):
        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AddField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=10, verbose_name='name', null=False, default=''),
            ),
        ]
        sqls = self.apply_operations_and_collect_sql('test', new_state, operations)
        print('\n'.join(sqls))
        sqls = [s for s in sqls if not s.startswith('--')]
        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "name" varchar(10) DEFAULT '' NOT NULL;''',
        ], sqls)

    @mock.patch('django_redshift_backend.base.DatabaseWrapper.data_types', BasePGDatabaseWrapper.data_types)
    @mock.patch('django_redshift_backend.base.DatabaseSchemaEditor._get_create_options', lambda self, model: '')
    def test_alter_type(self):
        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AlterField(
                model_name='Pony',
                name='weight',
                field=models.CharField(max_length=10, null=False, default=''),
            ),
        ]
        sqls = self.apply_operations_and_collect_sql('test', new_state, operations)
        print('\n'.join(sqls))
        sqls = [s for s in sqls if not s.startswith('--')]
        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "weight_tmp" varchar(10) DEFAULT '' NOT NULL;''',
            '''UPDATE test_pony SET "weight_tmp" = "weight";''',
            '''ALTER TABLE test_pony DROP COLUMN "weight" CASCADE;''',
            '''ALTER TABLE test_pony RENAME COLUMN "weight_tmp" TO "weight";''',
        ], sqls)

    @mock.patch('django_redshift_backend.base.DatabaseWrapper.data_types', BasePGDatabaseWrapper.data_types)
    @mock.patch('django_redshift_backend.base.DatabaseSchemaEditor._get_create_options', lambda self, model: '')
    def test_change_default(self):
        # https://github.com/jazzband/django-redshift-backend/issues/63
        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AddField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=10, verbose_name='name', null=False, default=''),
            ),
            migrations.AlterField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=10, verbose_name='name', null=False, default='blink'),
            ),
        ]
        sqls = self.apply_operations_and_collect_sql('test', new_state, operations)
        print('\n'.join(sqls))
        sqls = [s for s in sqls if not s.startswith('--')]
        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "name" varchar(10) DEFAULT '' NOT NULL;''',
            '''ALTER TABLE "test_pony" ADD COLUMN "name_tmp" varchar(10) DEFAULT 'blink' NOT NULL;''',
            '''UPDATE test_pony SET "name_tmp" = "name";''',
            '''ALTER TABLE test_pony DROP COLUMN "name" CASCADE;''',
            '''ALTER TABLE test_pony RENAME COLUMN "name_tmp" TO "name";''',
        ], sqls)

    @mock.patch('django_redshift_backend.base.DatabaseWrapper.data_types', BasePGDatabaseWrapper.data_types)
    @mock.patch('django_redshift_backend.base.DatabaseSchemaEditor._get_create_options', lambda self, model: '')
    def test_alter_notnull_to_nullable(self):
        # https://github.com/jazzband/django-redshift-backend/issues/63
        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AlterField(
                model_name='Pony',
                name='weight',
                field=models.FloatField(null=True),
            ),
        ]
        sqls = self.apply_operations_and_collect_sql('test', new_state, operations)
        print('\n'.join(sqls))
        sqls = [s for s in sqls if not s.startswith('--')]
        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "name_tmp" varchar(10) NULL;''',
            '''UPDATE "test_pony" SET "name_tmp"="name";''',
            '''ALTER TABLE "test_pony" DROP COLUMN "name";''',
            '''ALTER TABLE "test_pony" RENAME COLUMN "name_tmp" TO "name";''',
        ], sqls)

    def apply_operations_and_collect_sql(self, app_label, project_state, operations, atomic=True):
        from django.db.migrations.migration import Migration
        migration = Migration('name', app_label)
        migration.operations = operations
        with connection.schema_editor(collect_sql=True, atomic=atomic) as editor:
            migration.apply(project_state, editor, collect_sql=True)
            return editor.collected_sql
