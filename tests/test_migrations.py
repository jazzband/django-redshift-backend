import os
import contextlib
from unittest import mock

from django.db import migrations, models
from django.db.migrations.state import ProjectState
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

    @contextlib.contextmanager
    def collect_sql(self):
        collected_sql = []

        def execute(self, sql, params=()):
            sql = str(sql)
            ending = "" if sql.endswith(";") else ";"
            if params is not None:
                collected_sql.append((sql % tuple(map(self.quote_value, params))) + ending)
            else:
                collected_sql.append(sql + ending)
            return super(type(self), self).execute(sql, params)

        with mock.patch('django_redshift_backend.base.DatabaseSchemaEditor.execute', execute):
            yield collected_sql

        print('\n'.join(collected_sql))

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

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "name" varchar(10) DEFAULT '' NOT NULL;''',
            '''ALTER TABLE "test_pony" ALTER COLUMN "name" TYPE varchar(20);''',
            '''ALTER TABLE "test_pony" ALTER COLUMN "name" TYPE varchar(10);''',
        ], sqls)

    @mock.patch('django_redshift_backend.base.DatabaseWrapper.data_types', BasePGDatabaseWrapper.data_types)
    @mock.patch('django_redshift_backend.base.DatabaseSchemaEditor._get_create_options', lambda self, model: '')
    def test_alter_size_for_unique(self):
        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AddField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=10, default='', unique=True),
            ),
            migrations.AlterField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=20, default='', unique=True),
            ),
        ]

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "name" varchar(10) DEFAULT '' NOT NULL UNIQUE;''',
            '''ALTER TABLE "test_pony" DROP CONSTRAINT "test_pony_name_key";''',
            '''ALTER TABLE "test_pony" ALTER COLUMN "name" TYPE varchar(20);''',
            '''ALTER TABLE "test_pony" ADD CONSTRAINT "test_pony_name_key" UNIQUE ("name");'''
        ], sqls)

    @mock.patch('django_redshift_backend.base.DatabaseWrapper.data_types', BasePGDatabaseWrapper.data_types)
    @mock.patch('django_redshift_backend.base.DatabaseSchemaEditor._get_create_options', lambda self, model: '')
    def test_alter_size_for_pk(self):
        setup_operations = [migrations.CreateModel(
            'Pony',
            [
                ('name', models.CharField(max_length=10, default='', primary_key=True)),
            ],
        )]
        new_state = self.apply_operations('test', ProjectState(), setup_operations)

        operations = [
            migrations.AlterField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=20, default='', primary_key=True),
            ),
        ]

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        self.assertEqual([
            '''ALTER TABLE "test_pony" DROP CONSTRAINT "test_pony_name_key";''',
            '''ALTER TABLE "test_pony" ALTER COLUMN "name" TYPE varchar(20);''',
            '''ALTER TABLE "test_pony" ADD CONSTRAINT "test_pony_name_key" UNIQUE ("name");'''
        ], sqls)

    @mock.patch('django_redshift_backend.base.DatabaseWrapper.data_types', BasePGDatabaseWrapper.data_types)
    @mock.patch('django_redshift_backend.base.DatabaseSchemaEditor._get_create_options', lambda self, model: '')
    def test_alter_size_for_fk(self):
        setup_operations = [
            migrations.CreateModel(
                'Pony',
                [
                    # ('id', models.AutoField(primary_key=True)),
                    # ('name', models.CharField(max_length=10, unique=True)),
                    ('id', models.CharField(max_length=10, primary_key=True)),
                ],
            ),
            migrations.CreateModel(
                'Rider',
                [
                    ('id', models.AutoField(primary_key=True)),
                    ('pony', models.ForeignKey('Pony', models.CASCADE)),
                ],
            ),
        ]
        new_state = self.apply_operations('test', ProjectState(), setup_operations)

        operations = [
            migrations.AlterField(
                model_name='Pony',
                name='id',
                field=models.CharField(max_length=20, primary_key=True),
            ),
        ]

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        self.assertEqual([
            '''ALTER TABLE "test_pony" DROP CONSTRAINT "test_pony_name_key";''',
            '''ALTER TABLE "test_pony" ALTER COLUMN "name" TYPE varchar(20);''',
            '''ALTER TABLE "test_pony" ADD CONSTRAINT "test_pony_name_key" UNIQUE ("name");'''
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
            with self.collect_sql():
                self.apply_operations('test', new_state, operations)

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

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

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

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "weight_tmp" varchar(10) DEFAULT '' NOT NULL;''',
            '''UPDATE test_pony SET "weight_tmp" = "weight";''',
            '''ALTER TABLE test_pony DROP COLUMN "weight" CASCADE;''',
            '''ALTER TABLE test_pony RENAME COLUMN "weight_tmp" TO "weight";''',
        ], sqls)

    @mock.patch('django_redshift_backend.base.DatabaseWrapper.data_types', BasePGDatabaseWrapper.data_types)
    @mock.patch('django_redshift_backend.base.DatabaseSchemaEditor._get_create_options', lambda self, model: '')
    def test_alter_notnull_with_default(self):
        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AddField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=10, verbose_name='name', null=True),
            ),
            migrations.AlterField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=10, verbose_name='name', null=False, default=''),
            ),
        ]

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "name" varchar(10) NULL;''',
            '''ALTER TABLE "test_pony" ADD COLUMN "name_tmp" varchar(10) DEFAULT '' NOT NULL;''',
            '''UPDATE test_pony SET "name_tmp" = "name";''',
            '''ALTER TABLE test_pony DROP COLUMN "name" CASCADE;''',
            '''ALTER TABLE test_pony RENAME COLUMN "name_tmp" TO "name";''',
        ], sqls)

    # ## Django usually does not use in-database defaults
    # ## ref: https://github.com/django/django/blob/3.2.12/django/db/backends/base/schema.py#L524
    # ## django-redshift-backend also does not support in-database defaults
    @pytest.mark.skip('django-redshift-backend does not support in-database defaults')
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

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

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

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "weight_tmp" double precision NULL;''',
            '''UPDATE test_pony SET "weight_tmp" = "weight";''',
            '''ALTER TABLE test_pony DROP COLUMN "weight" CASCADE;''',
            '''ALTER TABLE test_pony RENAME COLUMN "weight_tmp" TO "weight";''',
        ], sqls)
