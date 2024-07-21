import os

os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'


from django.apps import apps  # noqa E402
apps.populate(['testapp'])


import contextlib
from unittest import mock

import pytest

from django_redshift_backend.base import BasePGDatabaseWrapper

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
                BasePGDatabaseWrapper.data_types,
            ), \
            mock.patch(
                'django_redshift_backend.base.DatabaseSchemaEditor._modify_params_for_redshift',
                lambda self, params: params
            ), \
            mock.patch(
                'django_redshift_backend.base.DatabaseSchemaEditor._get_create_options',
                lambda self, model: '',
            ):
            yield

    else:
        yield
