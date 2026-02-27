from django.db.backends.base.features import BaseDatabaseFeatures


class DatabaseFeatures(BaseDatabaseFeatures):
    minimum_database_version = (8,)  # Redshift is postgres 8.0.2

    # PostgreSQL-compatible features
    allows_group_by_select_index = True
    can_introspect_materialized_views = True
    has_real_datatype = True
    has_native_duration_field = True
    can_defer_constraint_checks = True
    has_select_for_update = False
    has_select_for_update_nowait = False
    has_select_for_update_of = False
    has_select_for_update_skip_locked = False
    can_release_savepoints = True
    supports_tablespaces = True
    supports_transactions = True
    can_introspect_autofield = True
    can_introspect_ip_address_field = True
    can_introspect_small_integer_field = True
    supports_paramstyle_pyformat = True
    greatest_least_ignores_nulls = False
    can_clone_databases = True
    supports_temporal_subtraction = True
    supports_slicing_ordering_in_compound = True
    create_test_procedure_without_params_sql = """
        CREATE FUNCTION test_procedure () RETURNS void AS $$
        DECLARE
            V_I INTEGER;
        BEGIN
            V_I := 1;
        END;
    $$ LANGUAGE plpgsql;"""
    create_test_procedure_with_int_param_sql = """
        CREATE FUNCTION test_procedure (P_I INTEGER) RETURNS void AS $$
        DECLARE
            V_I INTEGER;
        BEGIN
            V_I := P_I;
        END;
    $$ LANGUAGE plpgsql;"""
    create_test_table_with_composite_primary_key = """
        CREATE TABLE test_table_composite_pk (
            column_1 INTEGER NOT NULL,
            column_2 INTEGER NOT NULL,
            PRIMARY KEY(column_1, column_2)
        )
    """
    requires_casted_case_in_updates = True
    supports_over_clause = True
    supports_frame_range_fixed_distance = True
    supports_aggregate_filter_clause = (
        False  # Redshift doesn't support FILTER (WHERE ...)
    )
    supports_update_conflicts = False  # Redshift has no ON CONFLICT
    test_collations = {
        "ci": "und-ci-ks-ks",
        "non_default": "sv-x-icu",
        "swedish_ci": "sv-x-icu",
    }

    # Redshift-specific limitations
    can_return_id_from_insert = False
    can_return_ids_from_bulk_insert = False
    can_return_columns_from_insert = False
    can_return_rows_from_bulk_insert = False
    supports_column_check_constraints = False
    supports_table_check_constraints = False
    can_distinct_on_fields = False
    allows_group_by_selected_pks = False
    has_native_json_field = False  # Redshift stores JSON as varchar
    has_native_uuid_field = False  # Redshift stores UUID as varchar(36)
    supports_combined_alters = False
    can_rollback_ddl = False
    supports_comments = False
    supports_default_keyword_in_insert = False
    supports_default_keyword_in_bulk_insert = False
    supports_nulls_distinct_unique_constraints = False
    delete_can_self_reference_subquery = True
    supports_ignore_conflicts = False  # Redshift has no ON CONFLICT DO NOTHING
