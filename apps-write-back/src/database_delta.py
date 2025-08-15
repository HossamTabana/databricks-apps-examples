import logging
import os
from contextlib import contextmanager

import pandas as pd
from databricks import sql
from databricks.sdk.core import Config
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


load_dotenv()

WAREHOUSE_HTTP_PATH = os.getenv("WAREHOUSE_HTTP_PATH")
DELTA_CATALOG = os.getenv("UNITY_CATALOG_CATALOG")
DELTA_SCHEMA = os.getenv("UNITY_CATALOG_SCHEMA")


cfg = Config()


def _get_full_table_name(table_name: str) -> str:
    """Constructs the full table name including catalog and schema."""
    return f"{DELTA_CATALOG}.{DELTA_SCHEMA}.{table_name}"


@contextmanager
def get_connection():
    conn = sql.connect(
        server_hostname=cfg.host,
        http_path=WAREHOUSE_HTTP_PATH,
        credentials_provider=lambda: cfg.authenticate,
    )
    try:
        yield conn
    finally:
        conn.close()


def execute_query(query: str, params=None) -> pd.DataFrame:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            if cursor.description:
                df = cursor.fetchall_arrow().to_pandas()
                # Ensure all column names are lowercase
                df.columns = [x.lower() for x in df.columns]
                return df
            return pd.DataFrame()


def read_delta_table(table_name: str, limit: int = 1000) -> pd.DataFrame:
    full_table_name = _get_full_table_name(table_name)
    query = f"SELECT * FROM {full_table_name} ORDER BY compliance_id ASC LIMIT {limit}"
    df = execute_query(query)
    logger.info("Read %d rows from %s", len(df), full_table_name)
    return df


def form_write_to_delta(
    customer_name: str,
    equipment_model: str,
    service_date: str,
    issue_description: str,
    repair_status: str,
) -> int:
    table_name = _get_full_table_name("form_service_calls")
    query = f"""INSERT INTO {table_name} (
            customer_name,
            equipment_model,
            issue_description,
            repair_status,
            filed_at,
            created_at
        ) VALUES (?, ?, ?, ?, ?, current_timestamp())
    """
    params = (
        customer_name,
        equipment_model,
        issue_description,
        repair_status,
        service_date,
    )

    result_df = execute_query(query, params)

    if isinstance(result_df, pd.DataFrame) and not result_df.empty:
        # Some insert statements (like for Delta) might return information
        # in a DataFrame. Here we check for a column that indicates success.
        if "num_inserted_rows" in result_df.columns:
            rows_inserted = int(result_df["num_inserted_rows"].iloc[0])
            logger.info("Inserted %d row(s) into %s", rows_inserted, table_name)
            return rows_inserted

    logger.warning(
        "Could not determine number of rows inserted. The operation may have failed or returned an unexpected result."
    )
    return 0


def update_delta_records(
    df_updates: pd.DataFrame, table_name: str, pk_column: str
) -> int:
    if df_updates.empty:
        logger.warning(
            "Update DataFrame is empty. No changes will be made to %s.", table_name
        )
        return 0

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                update_cols = [col for col in df_updates.columns if col != pk_column]
                all_cols_for_values = [pk_column] + update_cols
                df_ordered = df_updates[all_cols_for_values]

                single_row_placeholders = (
                    f"({', '.join(['?'] * len(all_cols_for_values))})"
                )
                all_rows_placeholders = ", ".join(
                    [single_row_placeholders] * len(df_ordered)
                )

                quoted_cols_for_cte = ", ".join(
                    [f"`{col}`" for col in all_cols_for_values]
                )

                set_clause = ", ".join(
                    [f"target.`{col}` = updates.`{col}`" for col in update_cols]
                )

                full_table_name = _get_full_table_name(table_name)
                query = f"""
                    WITH updates({quoted_cols_for_cte}) AS (
                        VALUES {all_rows_placeholders}
                    )
                    MERGE INTO {full_table_name} AS target
                    USING updates
                    ON target.`{pk_column}` = updates.`{pk_column}`
                    WHEN MATCHED THEN
                        UPDATE SET {set_clause}
                """

                params_list = [
                    item
                    for row in df_ordered.itertuples(index=False, name=None)
                    for item in row
                ]

                logger.info(
                    "[DB] Updating %d records in %s using MERGE with CTE...",
                    len(df_ordered),
                    full_table_name,
                )

                cursor.execute(query, params_list)

                logger.info("[DB] Successfully merged records.")
                return len(df_updates)

    except Exception as e:
        logger.error("[DB] Error updating Delta table with MERGE: %s", e)
        raise


def dataframe_to_delta(df: pd.DataFrame) -> int:
    columns = [
        "pricing_id",
        "product_code",
        "region",
        "wholesale_price",
        "retail_price",
        "effective_from",
        "currency",
        "price_type",
    ]

    df_ordered = df[columns].copy()
    df_final = df_ordered.astype(str).replace(["nan", "NaT"], None)
    column_names = ", ".join(columns)
    single_row_placeholders = f"({', '.join(['?'] * len(columns))})"
    all_rows_placeholders = ", ".join([single_row_placeholders] * len(df_final))
    data_flat = [
        item for row in df_final.itertuples(index=False, name=None) for item in row
    ]
    table_name = _get_full_table_name("excel_prices")
    query = (
        f"INSERT OVERWRITE {table_name} ({column_names}) VALUES {all_rows_placeholders}"
    )

    with get_connection() as conn:
        with conn.cursor() as cursor:
            logger.info(
                "Overwriting %s with %d new rows in a single operation...",
                table_name,
                len(df_final),
            )
            cursor.execute(query, data_flat)
            logger.info("Successfully overwrote the table.")
            return len(df_final)
