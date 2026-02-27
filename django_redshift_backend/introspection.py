from django.db.backends.base.introspection import (
    BaseDatabaseIntrospection,
    FieldInfo,
    TableInfo,
)
from django.db.models import Index


class DatabaseIntrospection(BaseDatabaseIntrospection):
    # Maps type codes to Django Field types.
    data_types_reverse = {
        16: "BooleanField",
        17: "BinaryField",
        20: "BigIntegerField",
        21: "SmallIntegerField",
        23: "IntegerField",
        25: "TextField",
        700: "FloatField",
        701: "FloatField",
        869: "GenericIPAddressField",
        1042: "CharField",  # blank-padded
        1043: "CharField",
        1082: "DateField",
        1083: "TimeField",
        1114: "DateTimeField",
        1184: "DateTimeField",
        1186: "DurationField",
        1266: "TimeField",
        1700: "DecimalField",
        2950: "UUIDField",
        3802: "JSONField",
    }
    # A hook for subclasses.
    index_default_access_method = "btree"

    ignored_tables = []

    # Redshift uses "identity" instead of "nextval" for auto fields
    def get_field_type(self, data_type, description):
        field_type = super().get_field_type(data_type, description)
        if description.default and "identity" in description.default:
            if field_type == "IntegerField":
                return "AutoField"
            elif field_type == "BigIntegerField":
                return "BigAutoField"
            elif field_type == "SmallIntegerField":
                return "SmallAutoField"
        return field_type

    def get_table_description(self, cursor, table_name):
        """
        Return a description of the table with the DB-API cursor.description
        interface.
        """
        # Query the pg_catalog tables as cursor.description does not reliably
        # return the nullable property and information_schema.columns does not
        # contain details of materialized views.
        cursor.execute(
            """
            SELECT
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
        """,
            [table_name],
        )
        field_map = {}
        for column_name, is_nullable, column_default in cursor.fetchall():
            field_map[column_name] = {
                "null_ok": is_nullable,
                "default": column_default,
                # Redshift doesn't support user-defined collation
                "collation": None,
            }
        cursor.execute(
            "SELECT * FROM %s LIMIT 1" % self.connection.ops.quote_name(table_name)
        )
        return [
            FieldInfo(
                name=column.name,
                type_code=column.type_code,
                display_size=column.display_size,
                internal_size=column.internal_size,
                precision=column.precision,
                scale=column.scale,
                **field_map[column.name],
            )
            for column in cursor.description
        ]

    def get_sequences(self, cursor, table_name, table_fields=()):
        # Redshift uses IDENTITY, not sequences
        return []

    def get_relations(self, cursor, table_name):
        """
        Return a dictionary of {field_name: (field_name_other_table, other_table)}
        representing all relationships to the given table.
        """
        return {
            row[0]: (row[2], row[1]) for row in self.get_key_columns(cursor, table_name)
        }

    def get_key_columns(self, cursor, table_name):
        cursor.execute(
            """
            SELECT a1.attname, c2.relname, a2.attname
            FROM pg_constraint con
            LEFT JOIN pg_class c1 ON con.conrelid = c1.oid
            LEFT JOIN pg_class c2 ON con.confrelid = c2.oid
            LEFT JOIN
                pg_attribute a1 ON c1.oid = a1.attrelid AND a1.attnum = con.conkey[1]
            LEFT JOIN
                pg_attribute a2 ON c2.oid = a2.attrelid AND a2.attnum = con.confkey[1]
            WHERE
                c1.relname = %s AND
                con.contype = 'f' AND
                c1.relnamespace = c2.relnamespace AND
                pg_catalog.pg_table_is_visible(c1.oid)
        """,
            [table_name],
        )
        return cursor.fetchall()

    def get_constraints(self, cursor, table_name):
        """
        Retrieve any constraints or keys (unique, pk, fk, check, index) across
        one or more columns. Also retrieve the definition of expression-based
        indexes.
        """
        constraints = {}
        # Loop over the key table, collecting things as constraints.
        cursor.execute(
            """
            SELECT
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
        """,
            [table_name],
        )
        constraint_records = [
            (conname, conkey, conrelid, contype, used_cols)
            for (conname, conkey, conrelid, contype, used_cols) in cursor.fetchall()
        ]
        table_oid = list(constraint_records)[0][2]  # Assuming at least one constraint
        attribute_num_to_name_map = self._get_attribute_number_to_name_map_for_table(
            cursor, table_oid
        )

        for constraint, conkey, conrelid, kind, used_cols in constraint_records:
            constraints[constraint] = {
                "columns": [
                    attribute_num_to_name_map[column_id_int] for column_id_int in conkey
                ],
                "primary_key": kind == "p",
                "unique": kind in ["p", "u"],
                "foreign_key": tuple(used_cols.split(".", 1)) if kind == "f" else None,
                "check": kind == "c",
                "index": False,
                "definition": None,
                "options": None,
            }

        # Now get indexes
        cursor.execute(
            """
            SELECT
                c2.relname,
                idx.indrelid,
                idx.indkey,  -- type "int2vector", returns space-separated string
                idx.indisunique,
                idx.indisprimary
            FROM
                pg_catalog.pg_class c,
                pg_catalog.pg_class c2,
                pg_catalog.pg_index idx
            WHERE c.oid = idx.indrelid
                AND idx.indexrelid = c2.oid
                AND c.relname = %s
        """,
            [table_name],
        )
        index_records = [
            (index_name, indrelid, indkey, unique, primary)
            for (index_name, indrelid, indkey, unique, primary) in cursor.fetchall()
        ]
        for index_name, indrelid, indkey, unique, primary in index_records:
            if index_name not in constraints:
                constraints[index_name] = {
                    "columns": [
                        attribute_num_to_name_map[int(column_id_str)]
                        for column_id_str in indkey.split(" ")
                    ],
                    "orders": [],  # Not implemented
                    "primary_key": primary,
                    "unique": unique,
                    "foreign_key": None,
                    "check": False,
                    "index": True,
                    "type": Index.suffix,  # Not implemented - assume default type
                    "definition": None,  # Not implemented
                    "options": None,  # Not implemented
                }

        return constraints

    def _get_attribute_number_to_name_map_for_table(self, cursor, table_oid):
        cursor.execute(
            """
            SELECT
                attrelid,  -- table oid
                attnum,
                attname
            FROM pg_attribute
            WHERE pg_attribute.attrelid = %s
            ORDER BY attrelid, attnum;
        """,
            [table_oid],
        )
        return {attnum: attname for _, attnum, attname in cursor.fetchall()}

    # Based on Django 3.2 PostgreSQL backend
    def get_table_list(self, cursor):
        """Return a list of table and view names in the current database."""
        cursor.execute("""
            SELECT c.relname,
            CASE WHEN c.relkind IN ('m', 'v') THEN 'v' ELSE 't' END
            FROM pg_catalog.pg_class c
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('f', 'm', 'p', 'r', 'v')
                AND n.nspname NOT IN ('pg_catalog', 'pg_toast')
                AND pg_catalog.pg_table_is_visible(c.oid)
        """)
        return [
            TableInfo(*row)
            for row in cursor.fetchall()
            if row[0] not in self.ignored_tables
        ]

    def get_primary_key_column(self, cursor, table_name):
        """
        Return the name of the primary key column for the given table.
        """
        columns = self.get_primary_key_columns(cursor, table_name)
        return columns[0] if columns else None

    def get_primary_key_columns(self, cursor, table_name):
        """Return a list of primary key columns for the given table."""
        for constraint in self.get_constraints(cursor, table_name).values():
            if constraint["primary_key"]:
                return constraint["columns"]
        return None
