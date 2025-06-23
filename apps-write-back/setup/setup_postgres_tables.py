#!/usr/bin/env python3
"""
PostgreSQL Database Seeding Script for Databricks Apps

This script seeds a PostgreSQL database with example tables for demonstration
purposes. It is designed to work with PostgreSQL instances managed by
Databricks.

It prompts for:
- Databricks CLI Profile
- PostgreSQL connection details (hostname, database, schema)
- (Optional) A Databricks service principal client ID to grant permissions.

Authentication is handled automatically using the Databricks SDK to fetch
an OAuth token for the current user.

Required libraries: psycopg[binary], databricks-sdk, python-dotenv
You can install them using: pip install "psycopg[binary]" databricks-sdk python-dotenv
"""

import os
import sys
import textwrap

import psycopg
from databricks.sdk import WorkspaceClient
from dotenv import find_dotenv, load_dotenv
from psycopg import sql

# --- SQL Definitions for Tables ---

TABLE_DEFINITIONS = {
    "form_service_calls": {
        "create": """
        CREATE TABLE {schema}.form_service_calls (
            call_id BIGINT GENERATED ALWAYS AS IDENTITY,
            customer_name VARCHAR(100),
            equipment_model VARCHAR(50),
            issue_description TEXT,
            repair_status VARCHAR(20),
            created_at TIMESTAMP,
            filed_at TIMESTAMP
        );
        """,
        "insert": None,
        "rows_to_insert": 0,
    },
    "table_regional_compliance": {
        "create": """
        CREATE TABLE {schema}.table_regional_compliance (
           compliance_id VARCHAR(255) PRIMARY KEY,
           product_id VARCHAR(255),
           country_code VARCHAR(10),
           regulation_type VARCHAR(50),
           compliance_status VARCHAR(50),
           valid_from DATE,
           valid_until DATE,
           notes TEXT
        );
        """,
        "insert": """
        INSERT INTO {schema}.table_regional_compliance (compliance_id, product_id, country_code, regulation_type, compliance_status, valid_from, valid_until, notes) VALUES
        ('DE-2025-HP-001', 'VP-200-H', 'DE', 'ErP', 'Certified', '2025-01-15', '2027-01-15', 'Requires additional documentation for installation'),
        ('FR-2024-BL-002', 'VB-150-G', 'FR', 'RED', 'Pending', '2024-11-01', '2026-11-01', 'Awaiting final test results'),
        ('UK-2025-HP-003', 'VP-300-S', 'UK', 'Energy Label', 'Certified', '2025-02-01', '2028-02-01', 'A+++ efficiency rating confirmed'),
        ('NL-2024-SL-004', 'VS-250-T', 'NL', 'F-Gas', 'Expired', '2023-03-15', '2025-03-15', 'Renewal application submitted'),
        ('DE-2025-BL-005', 'VB-200-C', 'DE', 'ErP', 'Certified', '2025-01-10', '2027-01-10', 'Standard compliance achieved'),
        ('IT-2024-HP-006', 'VP-180-A', 'IT', 'Energy Label', 'Pending', '2024-12-01', '2026-12-01', 'Documentation under review'),
        ('ES-2025-SL-007', 'VS-300-R', 'ES', 'RED', 'Certified', '2025-03-01', '2027-03-01', 'All safety requirements met'),
        ('BE-2024-HP-008', 'VP-250-W', 'BE', 'F-Gas', 'Not Required', '2024-01-01', '2026-01-01', 'Product uses natural refrigerant'),
        ('AT-2025-BL-009', 'VB-180-D', 'AT', 'ErP', 'Certified', '2025-02-15', '2027-02-15', 'Energy efficiency standards exceeded'),
        ('CH-2024-HP-010', 'VP-220-E', 'CH', 'Energy Label', 'Certified', '2024-10-01', '2026-10-01', 'Swiss energy regulations compliant'),
        ('FR-2025-SL-011', 'VS-200-M', 'FR', 'F-Gas', 'Pending', '2025-01-20', '2027-01-20', 'Refrigerant leak test scheduled'),
        ('DE-2024-HP-012', 'VP-350-K', 'DE', 'RED', 'Certified', '2024-09-15', '2026-09-15', 'Electromagnetic compatibility verified'),
        ('UK-2025-BL-013', 'VB-220-P', 'UK', 'ErP', 'Expired', '2023-06-01', '2025-06-01', 'Recertification in progress'),
        ('NL-2025-SL-014', 'VS-180-Q', 'NL', 'Energy Label', 'Certified', '2025-04-01', '2028-04-01', 'High efficiency rating achieved'),
        ('IT-2024-HP-015', 'VP-280-L', 'IT', 'F-Gas', 'Certified', '2024-08-15', '2026-08-15', 'Low GWP refrigerant approved'),
        ('ES-2025-BL-016', 'VB-250-N', 'ES', 'ErP', 'Pending', '2025-03-15', '2027-03-15', 'Final efficiency testing required'),
        ('BE-2024-HP-017', 'VP-320-J', 'BE', 'RED', 'Certified', '2024-07-01', '2026-07-01', 'Radio frequency compliance confirmed'),
        ('AT-2025-SL-018', 'VS-220-B', 'AT', 'Energy Label', 'Not Required', '2025-01-01', '2027-01-01', 'Product category exempted'),
        ('CH-2024-BL-019', 'VB-300-F', 'CH', 'F-Gas', 'Certified', '2024-11-15', '2026-11-15', 'Swiss F-Gas regulations met'),
        ('FR-2025-HP-020', 'VP-240-G', 'FR', 'ErP', 'Certified', '2025-05-01', '2027-05-01', 'French energy efficiency standards achieved');
        """,
        "rows_to_insert": 20,
    },
    "excel_prices": {
        "create": """
        CREATE TABLE {schema}.excel_prices (
            pricing_id VARCHAR(255) PRIMARY KEY,
            product_code VARCHAR(255),
            region VARCHAR(50),
            wholesale_price DECIMAL(10,2),
            retail_price DECIMAL(10,2),
            effective_from DATE,
            currency VARCHAR(10),
            price_type VARCHAR(50)
        );
        """,
        "insert": None,
        "rows_to_insert": 0,
    },
}


def get_user_input(prompt, default=None):
    """Get user input with a default value."""
    prompt_text = f"{prompt} [{default}]: " if default else f"{prompt}: "
    user_input = input(prompt_text)
    return user_input.strip() or default


def get_connection(db_params):
    """Get a PostgreSQL connection."""
    print(f"\nAttempting to connect to PostgreSQL host '{db_params['host']}'...")
    try:
        conn = psycopg.connect(**db_params)
        conn.autocommit = True  # Set autocommit to handle DDL statements easily
        print("✓ Connection successful.")
        return conn
    except psycopg.Error as e:
        print(f"✗ Failed to connect to PostgreSQL: {e}")
        print(
            "Please check your connection details and ensure the database is accessible."
        )
        sys.exit(1)


def execute_sql(cursor, sql_statement, description=""):
    """Execute a single SQL statement and handle errors."""
    try:
        clean_sql = textwrap.dedent(sql_statement).strip()
        if not clean_sql:
            return True
        cursor.execute(clean_sql)
        if description:
            print(f"  ✓ {description}")
        return True
    except psycopg.Error as e:
        print(f"  ✗ {description} failed: {e}")
        return False


def table_exists(cursor, schema, table_name):
    """Check if a table exists in the given schema."""
    try:
        query = sql.SQL("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = %s AND table_name = %s
            );
        """)
        cursor.execute(query, (schema, table_name))
        return cursor.fetchone()[0]
    except psycopg.Error as e:
        print(f"  ! Warning: Could not check for table {table_name}: {e}")
        return False


def create_tables(conn, schema):
    """Create all the example tables."""
    print("\nCreating tables...")
    tables_created_or_updated = []
    tables_skipped = 0

    with conn.cursor() as cursor:
        # Ensure the schema exists
        execute_sql(
            cursor,
            f"CREATE SCHEMA IF NOT EXISTS {schema}",
            f"Ensuring schema '{schema}' exists",
        )

        for table_name, cmds in TABLE_DEFINITIONS.items():
            full_table_name_str = f"{schema}.{table_name}"
            print(f"\nProcessing table: {full_table_name_str}")

            if table_exists(cursor, schema, table_name):
                overwrite = get_user_input(
                    f"  ! Table '{full_table_name_str}' already exists. Overwrite? (y/N)",
                    "N",
                )
                if overwrite.lower() != "y":
                    print(f"  - Skipped '{table_name}'.")
                    tables_skipped += 1
                    continue
                # Drop table if overwrite is confirmed
                execute_sql(
                    cursor,
                    f"DROP TABLE {full_table_name_str};",
                    f"Dropping existing table '{table_name}'",
                )

            # Format SQL with the correct schema
            create_sql = cmds["create"].format(schema=schema)
            if execute_sql(cursor, create_sql, f"Creating table '{table_name}'"):
                if cmds.get("insert"):
                    insert_sql = cmds["insert"].format(schema=schema)
                    execute_sql(
                        cursor,
                        insert_sql,
                        f"Inserting {cmds['rows_to_insert']} rows into '{table_name}'",
                    )
                tables_created_or_updated.append(table_name)
            else:
                # If create fails, we consider it 'skipped' in the sense that it's not 'created'.
                tables_skipped += 1

    return tables_created_or_updated, tables_skipped


def grant_permissions(conn, db_name, schema, sp_id):
    """Grant required permissions to a Databricks service principal."""
    print(f"\nGranting permissions to service principal '{sp_id}'...")

    with conn.cursor() as cursor:
        # Use psycopg.sql for safe identifier quoting
        sp_id_sql = sql.Identifier(sp_id)
        db_name_sql = sql.Identifier(db_name)
        schema_sql = sql.Identifier(schema)

        print(
            "\nNote: This requires the 'databricks_auth' extension in your PostgreSQL DB."
        )

        # 1. Create extension
        execute_sql(
            cursor,
            "CREATE EXTENSION IF NOT EXISTS databricks_auth;",
            "Enabling 'databricks_auth' extension",
        )

        # 2. First, find where the pg_databricks_create_role function is located
        function_schema = None
        try:
            cursor.execute("""
                SELECT n.nspname as schema_name
                FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE p.proname = 'pg_databricks_create_role'
                LIMIT 1;
            """)
            result = cursor.fetchone()
            if result:
                function_schema = result[0]
                print(
                    f"  ✓ Found pg_databricks_create_role function in schema: {function_schema}"
                )
        except psycopg.Error:
            pass

        # 3. Create role for the service principal
        role_created = False

        if function_schema:
            # Use the discovered schema
            try:
                query = sql.SQL(
                    "SELECT {}.pg_databricks_create_role(%s::VARCHAR, 'SERVICE_PRINCIPAL'::VARCHAR);"
                ).format(sql.Identifier(function_schema))
                cursor.execute(query, (sp_id,))
                print(f"  ✓ Created role for service principal '{sp_id}'")
                role_created = True
            except psycopg.Error as e:
                error_msg = str(e)
                if "already exists" in error_msg:
                    print(f"  ✓ Role for service principal '{sp_id}' already exists")
                    role_created = True
                else:
                    print(
                        f"  ✗ Failed to create role using {function_schema}.pg_databricks_create_role: {e}"
                    )

        if not role_created:
            # Fallback: try common schemas
            role_queries = [
                "SELECT pg_databricks_create_role(%s::VARCHAR, 'SERVICE_PRINCIPAL'::VARCHAR);",
                "SELECT public.pg_databricks_create_role(%s::VARCHAR, 'SERVICE_PRINCIPAL'::VARCHAR);",
            ]

            for query in role_queries:
                try:
                    cursor.execute(query, (sp_id,))
                    print(f"  ✓ Created role for service principal '{sp_id}'")
                    role_created = True
                    break
                except psycopg.Error as e:
                    error_msg = str(e)
                    if "already exists" in error_msg:
                        print(
                            f"  ✓ Role for service principal '{sp_id}' already exists"
                        )
                        role_created = True
                        break
                    continue

            if not role_created:
                print("  ✗ Failed to create role for service principal")
                print(
                    "  ! Could not find or execute pg_databricks_create_role function"
                )
                return

        # 3. Grant privileges
        privileges = {
            "DATABASE": sql.SQL("GRANT CONNECT ON DATABASE {} TO {};").format(
                db_name_sql, sp_id_sql
            ),
            "SCHEMA": sql.SQL("GRANT USAGE, CREATE ON SCHEMA {} TO {};").format(
                schema_sql, sp_id_sql
            ),
            "TABLES": sql.SQL(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {};"
            ).format(schema_sql, sp_id_sql),
            "SEQUENCES": sql.SQL(
                "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA {} TO {};"
            ).format(schema_sql, sp_id_sql),
        }

        execute_sql(
            cursor,
            privileges["DATABASE"].as_string(cursor),
            f"Granting CONNECT on database '{db_name}'",
        )
        execute_sql(
            cursor,
            privileges["SCHEMA"].as_string(cursor),
            f"Granting USAGE, CREATE on schema '{schema}'",
        )
        execute_sql(
            cursor,
            privileges["TABLES"].as_string(cursor),
            "Granting table permissions (SELECT, INSERT, UPDATE, DELETE)",
        )
        execute_sql(
            cursor,
            privileges["SEQUENCES"].as_string(cursor),
            "Granting sequence permissions for IDENTITY columns",
        )

    print("\n✓ Permissions granting process complete.")


def main():
    """Main function to drive the script."""
    print("-" * 60)
    print("PostgreSQL Database Seeding Script for Databricks Apps")
    print("-" * 60)
    print("This script will create and populate tables in your PostgreSQL database.")
    print("Authentication will be handled using your Databricks profile.")

    # --- Gather User Input ---
    print("\nPlease provide the following configuration:")
    profile = get_user_input("Databricks CLI profile", "DEFAULT")

    db_params = {}

    while not db_params.get("host"):
        db_params["host"] = get_user_input("PostgreSQL hostname")
        if not db_params.get("host"):
            print("  ! Hostname is required.")

    db_params["dbname"] = get_user_input(
        "Database name", "databricks_postgres"
    )

    schema = get_user_input("Schema name", "public")

    # --- Get credentials from Databricks SDK ---
    try:
        print(f"\nFetching credentials using Databricks profile '{profile}'...")
        w = WorkspaceClient(profile=profile)
        db_params["user"] = w.current_user.me().user_name
        db_params["password"] = w.config.oauth_token().access_token
        print("✓ Credentials fetched successfully.")
    except Exception as e:
        print(f"✗ Failed to get Databricks credentials: {e}")
        print(
            "  Please ensure you are authenticated with the Databricks CLI ('databricks auth login')."
        )
        sys.exit(1)

    # --- Confirm Configuration ---
    print("\n--- Configuration Summary ---")
    print(f"Databricks Profile: {profile}")
    print(f"Hostname:           {db_params['host']}")
    print(f"Database:           {db_params['dbname']}")
    print(f"Username:           {db_params['user']} (from SDK)")
    print(f"Schema:             {schema}")
    print("-" * 29)

    if get_user_input("\nProceed with this configuration? (Y/n)", "Y").lower() != "y":
        print("Operation cancelled by user.")
        sys.exit(0)

    conn = None
    try:
        conn = get_connection(db_params)
        created_tables, skipped_tables = create_tables(conn, schema)

        print("\n--- Table Creation Summary ---")
        print(f"✓ Tables created/updated: {len(created_tables)}")
        print(f"- Tables skipped:         {skipped_tables}")
        print("-" * 30)

        if created_tables or skipped_tables > 0:
            print("\n--- Service Principal Permissions ---")
            grant_perm = get_user_input(
                "Grant permissions to a Databricks Service Principal? (y/N)", "N"
            )
            if grant_perm.lower() == "y":
                print(
                    "\nThe service principal client ID is a UUID like '602d47c2-20a3-4629-a3d8-b83861a227aa'."
                )
                while not (sp_id := get_user_input("Enter the service principal client ID")):
                    print("  ! Service principal client ID cannot be empty.")
                grant_permissions(conn, db_params["dbname"], schema, sp_id)
            else:
                print("\nSkipping permission grants.")

    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
    finally:
        if conn:
            conn.close()
            print("\n✓ Connection closed.")

    print("\nScript finished.")


if __name__ == "__main__":
    main()
