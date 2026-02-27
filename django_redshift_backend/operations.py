import json
import re
import uuid

from django.conf import settings
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.backends.utils import split_tzname_delta
from django.db.models.expressions import Col
from django.db.utils import NotSupportedError


class DatabaseOperations(BaseDatabaseOperations):
    cast_char_field_without_max_length = "varchar"
    explain_prefix = "EXPLAIN"
    explain_options = frozenset(
        [
            "ANALYZE",
            "BUFFERS",
            "COSTS",
            "SETTINGS",
            "SUMMARY",
            "TIMING",
            "VERBOSE",
            "WAL",
        ]
    )
    cast_data_types = {
        "AutoField": "integer",
        "BigAutoField": "bigint",
        "SmallAutoField": "smallint",
    }

    # EXTRACT format cannot be passed in parameters.
    _extract_format_re = re.compile(r"[A-Z_]+")

    def quote_name(self, name):
        if name.startswith('"') and name.endswith('"'):
            return name  # Quoting once is enough.
        return '"%s"' % name

    def no_limit_value(self):
        return None

    def max_name_length(self):
        # Redshift supports identifiers up to 127 characters
        return 127

    def prepare_sql_script(self, sql):
        return [sql]

    def set_time_zone_sql(self):
        return "SET TIME ZONE %s"

    def prep_for_iexact_query(self, x):
        return x

    # --- Temporal methods (Django 4.2+ signature: sql, params tuple API) ---

    def date_extract_sql(self, lookup_type, sql, params):
        if lookup_type == "week_day":
            # For consistency across backends, we return Sunday=1, Saturday=7.
            return f"EXTRACT(DOW FROM {sql}) + 1", params
        elif lookup_type == "iso_week_day":
            return f"EXTRACT(ISODOW FROM {sql})", params
        elif lookup_type == "iso_year":
            return f"EXTRACT(ISOYEAR FROM {sql})", params

        lookup_type = lookup_type.upper()
        if not self._extract_format_re.fullmatch(lookup_type):
            raise ValueError(f"Invalid lookup type: {lookup_type!r}")
        return f"EXTRACT({lookup_type} FROM {sql})", params

    def date_trunc_sql(self, lookup_type, sql, params, tzname=None):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"DATE_TRUNC(%s, {sql})", (lookup_type, *params)

    def _prepare_tzname_delta(self, tzname):
        tzname, sign, offset = split_tzname_delta(tzname)
        if offset:
            sign = "-" if sign == "+" else "+"
            return f"{tzname}{sign}{offset}"
        return tzname

    def _convert_sql_to_tz(self, sql, params, tzname):
        if tzname and settings.USE_TZ:
            tzname_param = self._prepare_tzname_delta(tzname)
            return f"{sql} AT TIME ZONE %s", (*params, tzname_param)
        return sql, params

    def datetime_cast_date_sql(self, sql, params, tzname):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"({sql})::date", params

    def datetime_cast_time_sql(self, sql, params, tzname):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"({sql})::time", params

    def datetime_extract_sql(self, lookup_type, sql, params, tzname):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return self.date_extract_sql(lookup_type, sql, params)

    def datetime_trunc_sql(self, lookup_type, sql, params, tzname):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"DATE_TRUNC(%s, {sql})", (lookup_type, *params)

    def time_extract_sql(self, lookup_type, sql, params):
        return self.date_extract_sql(lookup_type, sql, params)

    def time_trunc_sql(self, lookup_type, sql, params, tzname=None):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"DATE_TRUNC(%s, {sql})::time", (lookup_type, *params)

    # --- Redshift-specific overrides ---

    def last_insert_id(self, cursor, table_name, pk_name):
        """
        Amazon Redshift doesn't support RETURNING, so this method
        retrieves MAX(pk) after insertion as a workaround.

        NOTE: in some cases, MAX(pk) workaround does not work correctly.
        Bulk insertion makes non-contiguous IDs like: 1, 4, 7, 10, ...
        and single insertion after such bulk insertion generates strange
        id value like 2.
        """
        cursor.execute(
            "SELECT MAX({pk}) from {table}".format(
                pk=pk_name, table=self.quote_name(table_name)
            )
        )
        return cursor.fetchone()[0]

    def for_update_sql(self, nowait=False, skip_locked=False, of=(), no_key=False):
        raise NotSupportedError(
            "SELECT FOR UPDATE is not implemented for this database backend"
        )

    def deferrable_sql(self):
        # unused
        return ""

    def sequence_reset_sql(self, style, model_list):
        # impossible with Redshift to reset a sequence
        return []

    def get_db_converters(self, expression):
        converters = super().get_db_converters(expression)
        internal_type = expression.output_field.get_internal_type()
        if internal_type == "UUIDField":
            converters.append(self.convert_uuidfield_value)
        return converters

    def convert_uuidfield_value(self, value, expression, connection):
        if value is not None:
            value = uuid.UUID(value)
        return value

    def distinct_sql(self, fields, params):
        if fields:
            raise NotSupportedError(
                "DISTINCT ON fields is not supported by this database backend"
            )
        return ["DISTINCT"], []

    def adapt_integerfield_value(self, value, internal_type):
        return value

    def insert_statement(self, on_conflict=None):
        return "INSERT INTO"

    def on_conflict_suffix_sql(self, fields, on_conflict, update_fields, unique_fields):
        return ""

    # Copied from Django 5.0 postgresql/operations.py
    def prepare_join_on_clause(self, lhs_table, lhs_field, rhs_table, rhs_field):
        lhs_expr = Col(lhs_table, lhs_field)
        rhs_expr = Col(rhs_table, rhs_field)
        # Cast is not implemented for redshift.
        return lhs_expr, rhs_expr

    # Copied from Django 4.2 base/operations.py
    def adapt_json_value(self, value, encoder):
        return json.dumps(value, cls=encoder)

    # --- Methods from PostgreSQL backend needed for psycopg2 compatibility ---

    def lookup_cast(self, lookup_type, internal_type=None):
        lookup = "%s"
        if lookup_type in (
            "iexact",
            "contains",
            "icontains",
            "startswith",
            "istartswith",
            "endswith",
            "iendswith",
            "regex",
            "iregex",
        ):
            lookup = "%s::text"
        if lookup_type in ("iexact", "icontains", "istartswith", "iendswith"):
            lookup = "UPPER(%s)" % lookup
        return lookup

    def last_executed_query(self, cursor, sql, params):
        # https://www.psycopg.org/docs/cursor.html#cursor.query
        if cursor.query is not None:
            return cursor.query.decode()
        return None

    def sql_flush(self, style, tables, *, reset_sequences=False, allow_cascade=False):
        if not tables:
            return []
        sql_parts = [
            style.SQL_KEYWORD("TRUNCATE"),
            ", ".join(style.SQL_FIELD(self.quote_name(table)) for table in tables),
        ]
        if reset_sequences:
            sql_parts.append(style.SQL_KEYWORD("RESTART IDENTITY"))
        if allow_cascade:
            sql_parts.append(style.SQL_KEYWORD("CASCADE"))
        return ["%s;" % " ".join(sql_parts)]

    def bulk_insert_sql(self, fields, placeholder_rows):
        placeholder_rows_sql = (", ".join(row) for row in placeholder_rows)
        values_sql = ", ".join("(%s)" % sql for sql in placeholder_rows_sql)
        return "VALUES " + values_sql

    def adapt_datefield_value(self, value):
        return value

    def adapt_datetimefield_value(self, value):
        return value

    def adapt_timefield_value(self, value):
        return value

    def adapt_decimalfield_value(self, value, max_digits=None, decimal_places=None):
        return value

    def subtract_temporals(self, internal_type, lhs, rhs):
        if internal_type == "DateField":
            lhs_sql, lhs_params = lhs
            rhs_sql, rhs_params = rhs
            params = (*lhs_params, *rhs_params)
            return "(interval '1 day' * (%s - %s))" % (lhs_sql, rhs_sql), params
        return super().subtract_temporals(internal_type, lhs, rhs)

    def explain_query_prefix(self, format=None, **options):
        extra = {}
        if options:
            options = {
                name.upper(): "true" if value else "false"
                for name, value in options.items()
            }
            for valid_option in self.explain_options:
                value = options.pop(valid_option, None)
                if value is not None:
                    extra[valid_option.upper()] = value
        prefix = super().explain_query_prefix(format, **options)
        if format:
            extra["FORMAT"] = format
        if extra:
            prefix += " (%s)" % ", ".join("%s %s" % i for i in extra.items())
        return prefix

    def unification_cast_sql(self, output_field):
        internal_type = output_field.get_internal_type()
        if internal_type in ("TimeField", "UUIDField"):
            return (
                "CAST(%%s AS %s)" % output_field.db_type(self.connection).split("(")[0]
            )
        return "%s"
