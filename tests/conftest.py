import os

os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'


from django.apps import apps  # noqa E402
apps.populate(['testapp'])


import contextlib
from unittest import mock

import pytest

TEST_WITH_POSTGRES = os.environ.get('TEST_WITH_POSTGRES')
TEST_WITH_REDSHIFT = os.environ.get('TEST_WITH_REDSHIFT')

skipif_no_database = pytest.mark.skipif(
    not TEST_WITH_POSTGRES and not TEST_WITH_REDSHIFT,
    reason="no TEST_WITH_POSTGRES/TEST_WITH_REDSHIFT are found",
)
run_only_postgres = pytest.mark.skipif(
    not TEST_WITH_POSTGRES,
    reason="Test only for postgres",
)
run_only_redshift = pytest.mark.skipif(
    not TEST_WITH_REDSHIFT,
    reason="Test only for redshift",
)

# Standard PostgreSQL data types for local testing against PostgreSQL
_POSTGRES_DATA_TYPES = {
    "AutoField": "serial",
    "BigAutoField": "bigserial",
    "BinaryField": "bytea",
    "BooleanField": "boolean",
    "CharField": "varchar(%(max_length)s)",
    "DateField": "date",
    "DateTimeField": "timestamp with time zone",
    "DecimalField": "numeric(%(max_digits)s, %(decimal_places)s)",
    "DurationField": "interval",
    "FileField": "varchar(%(max_length)s)",
    "FilePathField": "varchar(%(max_length)s)",
    "FloatField": "double precision",
    "IntegerField": "integer",
    "BigIntegerField": "bigint",
    "IPAddressField": "inet",
    "GenericIPAddressField": "inet",
    "JSONField": "jsonb",
    "OneToOneField": "integer",
    "PositiveBigIntegerField": "bigint",
    "PositiveIntegerField": "integer",
    "PositiveSmallIntegerField": "smallint",
    "SlugField": "varchar(%(max_length)s)",
    "SmallAutoField": "smallserial",
    "SmallIntegerField": "smallint",
    "TextField": "text",
    "TimeField": "time",
    "UUIDField": "uuid",
}


@contextlib.contextmanager
def postgres_fixture():
    """A context manager that patches the database backend to use PostgreSQL
    for local testing.

    The purpose of the postgres_fixture context manager is to conditionally
    patch the database backend to use PostgreSQL for testing, but only if the
    TEST_WITH_POSTGRES variable is set to True.

    The reason for not using pytest.fixture in the current setup is due to the
    use of classes that inherit from TestCase. pytest fixtures do not directly
    integrate with Django's TestCase based tests.
    """
    if TEST_WITH_POSTGRES:
        with \
            mock.patch(
                'django_redshift_backend.base.DatabaseWrapper.data_types',
                _POSTGRES_DATA_TYPES,
            ), \
            mock.patch(
                'django_redshift_backend.schema.DatabaseSchemaEditor._modify_params_for_redshift',
                lambda self, params: params
            ), \
            mock.patch(
                'django_redshift_backend.schema.DatabaseSchemaEditor._get_create_options',
                lambda self, model: '',
            ):
            yield

    else:
        yield
