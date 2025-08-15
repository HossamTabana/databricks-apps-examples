#!/usr/bin/env python3
"""
Databricks Apps Writeback Example Application - Table Creation Script

This script creates example tables in Databricks and can optionally grant
permissions to a service principal for use with a Databricks Application.

It prompts for:
- Databricks CLI profile
- Catalog name
- Schema name
- SQL warehouse HTTP path
- (Optional) Service principal client ID for permissions

The script checks for existing tables and asks for confirmation before overwriting.
"""

import os
import sys
import textwrap

from databricks import sql
from databricks.sdk.core import Config

# --- SQL Definitions for Tables ---

# This dictionary holds the table names and their corresponding SQL commands.
# The structure allows for easy extension with more tables in the future.
TABLE_DEFINITIONS = {
    "form_service_calls": {
        "create": """
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.form_service_calls (
            call_id BIGINT GENERATED ALWAYS AS IDENTITY,
            customer_name VARCHAR(100),
            equipment_model VARCHAR(50),
            issue_description STRING,
            repair_status VARCHAR(20),
            filed_at TIMESTAMP,
            created_at TIMESTAMP
        )
        """,
        "insert": None,  # No initial data for this table
        "rows_to_insert": 0,
    },
    "table_regional_compliance": {
        "create": """
        CREATE OR REPLACE TABLE {catalog}.{schema}.table_regional_compliance (
           compliance_id VARCHAR(255) PRIMARY KEY,
           product_id VARCHAR(255),
           country_code VARCHAR(10),
           regulation_type VARCHAR(50),
           compliance_status VARCHAR(50),
           valid_from DATE,
           valid_until DATE,
           notes STRING
        )
        """,
        "insert": """
        INSERT INTO {catalog}.{schema}.table_regional_compliance 
        (compliance_id, product_id, country_code, regulation_type, compliance_status, valid_from, valid_until, notes) VALUES
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
        ('FR-2025-HP-020', 'VP-240-G', 'FR', 'ErP', 'Certified', '2025-05-01', '2027-05-01', 'French energy efficiency standards achieved')
        """,
        "rows_to_insert": 20,
    },
    "excel_prices": {
        "create": """
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.excel_prices (
            pricing_id STRING,
            product_code STRING,
            region STRING,
            wholesale_price STRING,
            retail_price STRING,
            effective_from STRING,
            currency STRING,
            price_type STRING
        )
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


def get_connection(profile, http_path):
    """Get a Databricks SQL connection, cached to prevent multiple connections."""
    print(f"\nAttempting to connect to Databricks using profile '{profile}'...")
    try:
        cfg = Config(profile=profile)
        conn = sql.connect(
            server_hostname=cfg.host,
            http_path=http_path,
            credentials_provider=lambda: cfg.authenticate,
        )
        print("✓ Connection successful.")
        return conn
    except Exception as e:
        print(f"✗ Failed to connect to Databricks: {e}")
        print("Please check your Databricks CLI configuration and SQL Warehouse Path.")
        sys.exit(1)


def execute_sql(conn, sql_statement, description=""):
    """Execute a single SQL statement and handle errors."""
    try:
        with conn.cursor() as cursor:
            # Use textwrap.dedent to clean up multi-line SQL strings
            clean_sql = textwrap.dedent(sql_statement).strip()
            if not clean_sql:
                return True

            cursor.execute(clean_sql)
            if description:
                print(f"  ✓ {description}")
        return True
    except Exception as e:
        print(f"  ✗ {description} failed: {e}")
        return False


def table_exists(conn, catalog, schema, table_name):
    """Check if a table exists in the given catalog and schema."""
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW TABLES IN {catalog}.{schema} LIKE '{table_name}'")
            return cursor.fetchone() is not None
    except Exception as e:
        print(f"  ! Warning: Could not check for table {table_name}: {e}")
        # Assume it doesn't exist to be safe, but warn the user.
        return False


def create_tables(conn, catalog, schema):
    """Create all the example tables defined in TABLE_DEFINITIONS."""
    print("\nCreating tables...")
    tables_created_or_updated = []
    tables_skipped = 0

    for table_name, sql_cmds in TABLE_DEFINITIONS.items():
        print(f"\nProcessing table: {catalog}.{schema}.{table_name}")

        # Check if table exists and ask for overwrite confirmation
        if table_exists(conn, catalog, schema, table_name):
            overwrite = get_user_input(
                f"  ! Table '{table_name}' already exists. Overwrite? (y/N)", "N"
            )
            if overwrite.lower() != "y":
                print(f"  - Skipped '{table_name}'.")
                tables_skipped += 1
                continue

        # Format SQL with the correct catalog and schema
        create_sql = sql_cmds["create"].format(catalog=catalog, schema=schema)

        # Execute CREATE statement
        if execute_sql(conn, create_sql, f"Creating/Replacing table '{table_name}'"):
            # If creation is successful, execute INSERT statement if it exists
            if sql_cmds.get("insert"):
                insert_sql = sql_cmds["insert"].format(catalog=catalog, schema=schema)
                execute_sql(
                    conn,
                    insert_sql,
                    f"Inserting {sql_cmds['rows_to_insert']} rows into '{table_name}'",
                )
            tables_created_or_updated.append(table_name)
        else:
            # If create failed, we consider it skipped
            tables_skipped += 1

    return tables_created_or_updated, tables_skipped


def grant_permissions(conn, catalog, schema, table_list, service_principal_id):
    """Grant required permissions to a service principal."""
    print(f"\nGranting permissions to service principal '{service_principal_id}'...")

    success = True

    # Grant on Catalog
    sql_catalog = (
        f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{service_principal_id}`"
    )
    if not execute_sql(conn, sql_catalog, f"Granting USE CATALOG on '{catalog}'"):
        success = False

    # Grant on Schema
    sql_schema = (
        f"GRANT USE SCHEMA ON SCHEMA `{catalog}`.`{schema}` TO `{service_principal_id}`"
    )
    if not execute_sql(conn, sql_schema, f"Granting USE SCHEMA on '{schema}'"):
        success = False

    # Grant on Tables
    for table_name in table_list:
        full_table_name = f"`{catalog}`.`{schema}`.`{table_name}`"
        sql_table = f"GRANT MODIFY, SELECT ON TABLE {full_table_name} TO `{service_principal_id}`"
        if not execute_sql(
            conn, sql_table, f"Granting MODIFY, SELECT on '{table_name}'"
        ):
            success = False

    if success:
        print("\n✓ All permissions granted successfully.")
    else:
        print("\n✗ Some permissions failed to grant. Please review the errors above.")


def main():
    """Main function to drive the script."""
    print("-" * 60)
    print("Databricks Apps Writeback Example - Table Creation Script")
    print("-" * 60)
    print(
        "This script will create and populate 3 tables in your Databricks workspace using your CLI credentials."
    )
    print(
        "You will be prompted for your configuration details if not found in your environment."
    )

    # --- Gather User Input ---
    print("\nPlease provide the following configuration:")
    profile = get_user_input("Databricks CLI profile", "DEFAULT")
    catalog = get_user_input("Catalog name", "main")
    schema = get_user_input("Schema name", "default")

    # Warehouse HTTP path is required
    http_path = None
    while not http_path:
        http_path = get_user_input(
            "SQL Warehouse HTTP Path, ex: '/sql/1.0/warehouses/762f1d756f0424f6'"
        )
        if not http_path:
            print("  ! SQL Warehouse HTTP Path is required.")

    # --- Confirm Configuration ---
    print("\n--- Configuration Summary ---")
    print(f"Profile:            {profile}")
    print(f"SQL Warehouse Path: {http_path}")
    print(f"Target Location:    {catalog}.{schema}")
    print("\n--- Data Summary ---")
    total_rows = sum(t["rows_to_insert"] for t in TABLE_DEFINITIONS.values())
    print(f"Tables to create:   {len(TABLE_DEFINITIONS)}")
    print(f"Sample data rows:   {total_rows}")
    print("-" * 29)

    if get_user_input("\nProceed with this configuration? (Y/n)", "Y").lower() != "y":
        print("Operation cancelled by user.")
        sys.exit(0)

    # --- Execute Operations ---
    conn = None
    try:
        conn = get_connection(profile, http_path)

        # Create tables
        created_tables, skipped_tables = create_tables(conn, catalog, schema)
        print("\n--- Table Creation Summary ---")
        print(f"✓ Tables created/updated: {len(created_tables)}")
        print(f"- Tables skipped:         {skipped_tables}")
        print("-" * 30)

        # Ask to grant permissions if any tables were actually created/updated
        if created_tables:
            print("\n--- Service Principal Permissions ---")
            grant_perm = get_user_input(
                "Do you want to grant permissions to an App Service Principal? (y/N)",
                "N",
            )
            if grant_perm.lower() == "y":
                print(
                    "\nThe service principal client ID is a UUID like '58fe4a02-16f8-4687-ae6c-2978a3637a52'."
                )
                print(
                    "In your Databricks App settings, find the 'DATABRICKS_CLIENT_ID' variable under the 'Environment' tab."
                )
                print(
                    "You can also run this script again at a later point to grant the permissions."
                )

                while not (sp_id := get_user_input("Enter the service principal client ID")):
                    print("  ! Service principal client ID cannot be empty.")

                grant_permissions(conn, catalog, schema, created_tables, sp_id)
            else:
                print("\nSkipping permission grants.")

    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
    finally:
        if conn:
            conn.close()
            print("\n✓ Connection closed.")

    print("Script finished.")


if __name__ == "__main__":
    main()
