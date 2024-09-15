import contextlib
from unittest import mock

from django.db import migrations, models
from django.db.migrations.state import ProjectState
import pytest

from test_base import OperationTestBase
from conftest import skipif_no_database, postgres_fixture, TEST_WITH_POSTGRES, TEST_WITH_REDSHIFT


@skipif_no_database
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

    @postgres_fixture()
    def test_alter_size_with_nullable(self):
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
                field=models.CharField(max_length=20, verbose_name='name', null=True),
            ),
            migrations.AlterField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=10, verbose_name='name', null=True),
            ),
        ]

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        self.assertEqual([
            # add column
            '''ALTER TABLE "test_pony" ADD COLUMN "name" varchar(10) NULL;''',
            # increase size
            '''ALTER TABLE "test_pony" ALTER COLUMN "name" TYPE varchar(20);''',
            # decrease size
            '''ALTER TABLE "test_pony" ALTER COLUMN "name" TYPE varchar(10);''',
        ], sqls)

    @postgres_fixture()
    def test_alter_size_with_default(self):
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
                field=models.CharField(max_length=20, verbose_name='name', default=''),
            ),
            migrations.AlterField(
                model_name='Pony',
                name='name',
                field=models.CharField(max_length=10, verbose_name='name', default=''),
            ),
        ]

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        self.assertEqual([
            # add column
            '''ALTER TABLE "test_pony" ADD COLUMN "name" varchar(10) DEFAULT '' NOT NULL;''',
            # increase size
            '''ALTER TABLE "test_pony" ALTER COLUMN "name" TYPE varchar(20);''',
            # decrease size
            '''ALTER TABLE "test_pony" ADD COLUMN "name_tmp" varchar(10) DEFAULT '' NOT NULL;''',
            '''UPDATE test_pony SET "name_tmp" = "name" WHERE "name" IS NOT NULL;''',
            '''ALTER TABLE test_pony DROP COLUMN "name" CASCADE;''',
            '''ALTER TABLE test_pony RENAME COLUMN "name_tmp" TO "name";''',
        ], sqls)

    @postgres_fixture()
    def test_add_unique_column(self):
        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AddField(
                model_name='Pony',
                name='name_with_default',
                field=models.CharField(max_length=10, default='', unique=True),
            ),
            migrations.AddField(
                model_name='Pony',
                name='name_with_nullable',
                field=models.CharField(max_length=10, null=True, unique=True),
            ),
        ]

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "name_with_default" varchar(10) DEFAULT '' NOT NULL;''',
            '''ALTER TABLE "test_pony" ADD COLUMN "name_with_nullable" varchar(10) NULL;''',
            '''ALTER TABLE "test_pony" ADD CONSTRAINT "test_pony_name_with_default_b3620670_uniq" UNIQUE ("name_with_default");''',
            '''ALTER TABLE "test_pony" ADD CONSTRAINT "test_pony_name_with_nullable_d1043f78_uniq" UNIQUE ("name_with_nullable");''',
        ], sqls)

    @postgres_fixture()
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
            '''ALTER TABLE "test_pony" ADD COLUMN "name" varchar(10) DEFAULT '' NOT NULL;''',
            # ADD UNIQUE "name"
            # DROP UNIQUE "name"
            '''ALTER TABLE "test_pony" ALTER COLUMN "name" TYPE varchar(20);''',
            '''ALTER TABLE "test_pony" ADD CONSTRAINT "test_pony_name_2c070d2a_uniq" UNIQUE ("name");'''
        ], sqls)

    @postgres_fixture()
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
            '''ALTER TABLE "test_pony" DROP CONSTRAINT "test_pony_pkey";''',
            '''ALTER TABLE "test_pony" ALTER COLUMN "name" TYPE varchar(20);''',
            '''ALTER TABLE "test_pony" ADD CONSTRAINT "test_pony_name_2c070d2a_pk" PRIMARY KEY ("name");''',
        ], sqls)

    @postgres_fixture()
    def test_alter_size_for_fk(self):
        setup_operations = [
            migrations.CreateModel(
                'Pony',
                [
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
            '''ALTER TABLE "test_rider" DROP CONSTRAINT "test_rider_pony_id_3c028c84_fk_test_pony_id";''',
            '''ALTER TABLE "test_pony" DROP CONSTRAINT "test_pony_pkey";''',
            '''ALTER TABLE "test_pony" ALTER COLUMN "id" TYPE varchar(20);''',
            '''ALTER TABLE "test_pony" ADD CONSTRAINT "test_pony_id_f5124350_pk" PRIMARY KEY ("id");''',
            '''ALTER TABLE "test_rider" ALTER COLUMN "pony_id" TYPE varchar(20);''',
            ('''ALTER TABLE "test_rider" ADD CONSTRAINT "test_rider_pony_id_3c028c84_fk"'''
                ''' FOREIGN KEY ("pony_id") REFERENCES "test_pony" ("id");'''),
        ], sqls)

    @postgres_fixture()
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

    @postgres_fixture()
    def test_add_notnull_without_default_on_backwards(self):
        project_state = self.set_up_test_model('test')
        operations = [
            migrations.AlterField(
                model_name='Pony',
                name='weight',
                field=models.FloatField(null=True),
            ),
        ]
        new_state = project_state.clone()
        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "weight_tmp" double precision NULL;''',
            '''UPDATE test_pony SET "weight_tmp" = "weight" WHERE "weight" IS NOT NULL;''',
            '''ALTER TABLE test_pony DROP COLUMN "weight" CASCADE;''',
            '''ALTER TABLE test_pony RENAME COLUMN "weight_tmp" TO "weight";''',
        ], sqls)

        with self.collect_sql() as sqls:
            self.unapply_operations('test', project_state, operations)

        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "weight_tmp" double precision DEFAULT 0.0 NOT NULL;''',
            '''UPDATE test_pony SET "weight_tmp" = "weight" WHERE "weight" IS NOT NULL;''',
            '''ALTER TABLE test_pony DROP COLUMN "weight" CASCADE;''',
            '''ALTER TABLE test_pony RENAME COLUMN "weight_tmp" TO "weight";''',
        ], sqls)

    @postgres_fixture()
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

    @pytest.mark.skip('django-redshift-backend does not support in-database defaults')
    @postgres_fixture()
    def test_add_db_default(self):
        from django.db.models.functions import Now

        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AddField(
                model_name='Pony',
                name='birthday',
                field=models.DateTimeField(null=False, db_default=Now()),
            ),
        ]

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "birthday" timestamp with time zone DEFAULT now() NOT NULL;''',
        ], sqls)

    @postgres_fixture()
    def test_add_binary(self):
        from django_redshift_backend.base import DatabaseWrapper, _remove_length_from_type

        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AddField(
                model_name='Pony',
                name='hash',
                field=models.BinaryField(
                    max_length=10,
                    verbose_name='hash',
                    null=False,
                    default=b'\x80\x00',
                ),
            ),
        ]

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        bin_type = DatabaseWrapper.data_types['BinaryField'] % {"max_length": 10}
        bin_cast = _remove_length_from_type(bin_type)
        if TEST_WITH_POSTGRES:
            default = fr"DEFAULT '\200\000'::{bin_cast}"
        elif TEST_WITH_REDSHIFT:
            default = fr"DEFAULT to_varbyte('8000', 'hex')::{bin_cast}"

        self.assertEqual([
            f'''ALTER TABLE "test_pony" ADD COLUMN "hash" {bin_type} {default} NOT NULL;''',
        ], sqls)

    @postgres_fixture()
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
            '''UPDATE test_pony SET "weight_tmp" = "weight" WHERE "weight" IS NOT NULL;''',
            '''ALTER TABLE test_pony DROP COLUMN "weight" CASCADE;''',
            '''ALTER TABLE test_pony RENAME COLUMN "weight_tmp" TO "weight";''',
        ], sqls)

    @postgres_fixture()
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
            '''UPDATE test_pony SET "name_tmp" = "name" WHERE "name" IS NOT NULL;''',
            '''ALTER TABLE test_pony DROP COLUMN "name" CASCADE;''',
            '''ALTER TABLE test_pony RENAME COLUMN "name_tmp" TO "name";''',
        ], sqls)

    # ## Django usually does not use in-database defaults
    # ## ref: https://github.com/django/django/blob/3.2.12/django/db/backends/base/schema.py#L524
    # ## django-redshift-backend also does not support in-database defaults
    @pytest.mark.skip('django-redshift-backend does not support in-database defaults')
    @postgres_fixture()
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

    @postgres_fixture()
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
            '''UPDATE test_pony SET "weight_tmp" = "weight" WHERE "weight" IS NOT NULL;''',
            '''ALTER TABLE test_pony DROP COLUMN "weight" CASCADE;''',
            '''ALTER TABLE test_pony RENAME COLUMN "weight_tmp" TO "weight";''',
        ], sqls)

    @postgres_fixture()
    def test_alter_type_char_to_binary(self):
        from django_redshift_backend.base import DatabaseWrapper, _remove_length_from_type

        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AddField(
                model_name='Pony',
                name='hash',
                field=models.CharField(max_length=10, verbose_name='hash', null=False, default=''),
            ),
            migrations.AlterField(
                model_name='Pony',
                name='hash',
                field=models.BinaryField(
                    max_length=10,
                    verbose_name='hash',
                    null=False,
                    default=b'\x80\x00',
                ),
            ),
        ]

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        bin_type = DatabaseWrapper.data_types['BinaryField'] % {"max_length": 10}
        bin_cast = _remove_length_from_type(bin_type)
        if TEST_WITH_POSTGRES:
            default = fr"DEFAULT '\200\000'::{bin_cast}"
        elif TEST_WITH_REDSHIFT:
            default = fr"DEFAULT to_varbyte('8000', 'hex')::{bin_cast}"

        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "hash" varchar(10) DEFAULT '' NOT NULL;''',
            f'''ALTER TABLE "test_pony" ADD COLUMN "hash_tmp" {bin_type} {default} NOT NULL;''',
            f'''UPDATE test_pony SET "hash_tmp" = "hash"::{bin_cast} WHERE "hash" IS NOT NULL;''',
            '''ALTER TABLE test_pony DROP COLUMN "hash" CASCADE;''',
            '''ALTER TABLE test_pony RENAME COLUMN "hash_tmp" TO "hash";''',
        ], sqls)

    @postgres_fixture()
    def test_alter_type_binary_to_char(self):
        from django_redshift_backend.base import DatabaseWrapper, _remove_length_from_type

        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AddField(
                model_name='Pony',
                name='hash',
                field=models.BinaryField(
                    max_length=10,
                    verbose_name='hash',
                    null=False,
                    default=b'\x80\x00',
                ),
            ),
            migrations.AlterField(
                model_name='Pony',
                name='hash',
                field=models.CharField(max_length=10, verbose_name='hash', null=False, default=''),
            ),
        ]

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        bin_type = DatabaseWrapper.data_types['BinaryField'] % {"max_length": 10}
        bin_cast = _remove_length_from_type(bin_type)
        if TEST_WITH_POSTGRES:
            default = fr"DEFAULT '\200\000'::{bin_cast}"
        elif TEST_WITH_REDSHIFT:
            default = fr"DEFAULT to_varbyte('8000', 'hex')::{bin_cast}"

        self.assertEqual([
            f'''ALTER TABLE "test_pony" ADD COLUMN "hash" {bin_type} {default} NOT NULL;''',
            '''ALTER TABLE "test_pony" ADD COLUMN "hash_tmp" varchar(10) DEFAULT '' NOT NULL;''',
            '''UPDATE test_pony SET "hash_tmp" = "hash"::varchar WHERE "hash" IS NOT NULL;''',
            '''ALTER TABLE test_pony DROP COLUMN "hash" CASCADE;''',
            '''ALTER TABLE test_pony RENAME COLUMN "hash_tmp" TO "hash";''',
        ], sqls)

    @postgres_fixture()
    def test_foreign_key_to_id(self):
        new_state = self.set_up_test_model('test')
        operations = [
            migrations.CreateModel(
                'Rider',
                [
                    ('id', models.AutoField(primary_key=True)),
                    ('pony', models.ForeignKey('Pony', models.CASCADE)),
                ],
            ),
        ]
        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        if TEST_WITH_POSTGRES:
            identity = "serial"
        elif TEST_WITH_REDSHIFT:
            identity = "integer identity(1, 1)"

        self.assertEqual([
            f'''CREATE TABLE "test_rider" ("id" {identity} NOT NULL PRIMARY KEY, "pony_id" integer NOT NULL) ;''',
            '''ALTER TABLE "test_rider" ADD CONSTRAINT "test_rider_pony_id_3c028c84_fk_test_pony_id"'''
            ''' FOREIGN KEY ("pony_id") REFERENCES "test_pony" ("id");''',
        ], sqls)

    @postgres_fixture()
    def test_foreign_key_to_non_id(self):
        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AddField(
                model_name='Pony',
                name='remote',
                field=models.IntegerField(unique=True, null=True),
            ),
            migrations.CreateModel(
                'Rider',
                [
                    ('id', models.AutoField(primary_key=True)),
                    ('pony_remote', models.ForeignKey('Pony', on_delete=models.CASCADE, to_field="remote")),
                ],
            ),
        ]
        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        if TEST_WITH_POSTGRES:
            identity = "serial"
        elif TEST_WITH_REDSHIFT:
            identity = "integer identity(1, 1)"

        self.assertEqual([
            '''ALTER TABLE "test_pony" ADD COLUMN "remote" integer NULL;''',
            f'''CREATE TABLE "test_rider" ("id" {identity} NOT NULL PRIMARY KEY, "pony_remote_id" integer NOT NULL) ;''',
            '''ALTER TABLE "test_pony" ADD CONSTRAINT "test_pony_remote_e347b432_uniq" UNIQUE ("remote");''',
            '''ALTER TABLE "test_rider" ADD CONSTRAINT "test_rider_pony_remote_id_269d66d9_fk_test_pony_remote" FOREIGN KEY ("pony_remote_id") REFERENCES "test_pony" ("remote");'''
        ], sqls)

    @postgres_fixture()
    def test_add_json(self):
        from django_redshift_backend.base import DatabaseWrapper

        new_state = self.set_up_test_model('test')
        operations = [
            migrations.AddField(
                model_name='Pony',
                name='structure',
                field=models.JSONField(
                    verbose_name='json data',
                    null=False,
                    default={"key1": "value", "key2": 1},
                ),
            ),
        ]

        with self.collect_sql() as sqls:
            self.apply_operations('test', new_state, operations)

        data_type = DatabaseWrapper.data_types['JSONField']
        default = """DEFAULT '{"key1": "value", "key2": 1}'"""

        self.assertEqual([
            f'''ALTER TABLE "test_pony" ADD COLUMN "structure" {data_type} {default} NOT NULL;''',
        ], sqls)
