import logging
import os
import time
import urllib.parse
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine.base import Connection
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.pool import QueuePool
from sqlalchemy.sql.expression import TextClause

logger = logging.getLogger(__name__)


def _get_full_table_name(table_name: str) -> str:
    """Constructs the full table name including schema if it's defined."""
    if db.schema:
        return f'"{db.schema}"."{table_name}"'
    return f'"{table_name}"'


class Database:
    def __init__(self) -> None:
        load_dotenv()
        self.schema = os.getenv("POSTGRES_SCHEMA")
        databricks_profile = os.getenv("DATABRICKS_PROFILE")
        if databricks_profile:
            self.cfg = Config(profile=databricks_profile)
            self.workspace_client = WorkspaceClient(profile=databricks_profile)
        else:
            self.cfg = Config()
            self.workspace_client = WorkspaceClient()
        self.postgres_password = None
        self.last_password_refresh = 0
        postgres_host = os.getenv("POSTGRES_HOST")
        postgres_port = int(os.getenv("POSTGRES_PORT", "5432"))
        postgres_database = os.getenv("POSTGRES_DATABASE", "databricks_postgres")
        is_deployed = os.getenv("DATABRICKS_APP_NAME") is not None
        raw_username = None
        if is_deployed:
            raw_username = self.cfg.client_id

        if not raw_username:
            try:
                current_user = self.workspace_client.current_user.me()
                raw_username = current_user.user_name
                if not raw_username:
                    raise ValueError(
                        "Could not determine postgres_username from current user. Ensure OAuth U2M authentication is configured."
                    )
            except Exception as e:
                profile_info = (
                    f" with profile '{databricks_profile}'"
                    if databricks_profile
                    else " with default profile"
                )
                raise ValueError(
                    f"Failed to get current user for local development{profile_info}. Ensure you have run 'databricks auth login' for the correct workspace and have proper OAuth U2M authentication configured: {e}"
                )

        if not raw_username:
            raise ValueError(
                "Could not determine postgres_username. Ensure Databricks authentication is configured."
            )

        postgres_username = urllib.parse.quote_plus(raw_username)
        db_url = f"postgresql+psycopg://{postgres_username}:@{postgres_host}:{postgres_port}/{postgres_database}?sslmode=require"
        self.engine = create_engine(
            db_url,
            poolclass=QueuePool,
            pool_size=20,
            max_overflow=30,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_timeout=30,
            connect_args={
                "connect_timeout": 10,
            },
        )
        event.listen(self.engine, "do_connect", self._provide_token)
        event.listen(self.engine, "connect", self._log_connect)
        event.listen(self.engine, "checkout", self._log_checkout)

    def _log_connect(self, dbapi_connection: Any, connection_record: Any) -> None:
        """Log when a new database connection is created"""
        logger.info("[DB] New database connection created")

    def _log_checkout(
        self, dbapi_connection: Any, connection_record: Any, connection_proxy: Any
    ) -> None:
        """Log when a connection is checked out from the pool"""
        logger.info("[DB] Connection checked out from pool")

    def _provide_token(
        self, dialect: Dialect, conn_rec: Any, cargs: Tuple, cparams: Dict
    ) -> None:
        if (
            self.postgres_password is None
            or time.time() - self.last_password_refresh > 900
        ):
            logger.info("[DB] Refreshing PostgreSQL OAuth token")
            start_time = time.time()
            try:
                token_info = self.workspace_client.config.oauth_token()
                if token_info is None:
                    err_msg = "OAuth token refresh failed: provider returned None for token_info."
                    logger.error(err_msg)
                    raise ValueError(err_msg)
                access_token = token_info.access_token
                if not access_token:
                    err_msg = (
                        "OAuth token refresh failed: access_token is None or empty."
                    )
                    logger.error(err_msg)
                    raise ValueError(err_msg)
                self.postgres_password = access_token
                self.last_password_refresh = time.time()
                refresh_duration = (time.time() - start_time) * 1000
                logger.info(
                    f"[DB] OAuth token refresh completed in {refresh_duration:.2f}ms"
                )
            except Exception as e:
                logger.error(f"Error refreshing OAuth token: {e}")
                raise
        else:
            logger.info(
                f"[DB] Reusing cached OAuth token (age: {time.time() - self.last_password_refresh:.0f}s)"
            )
        if not self.postgres_password:
            final_err_msg = "FATAL: PostgreSQL password (OAuth token) is None or empty before setting connection params. Token acquisition likely failed."
            logger.error(final_err_msg)
            raise ValueError(final_err_msg)
        cparams["password"] = self.postgres_password

    @contextmanager
    def get_connection(self) -> Generator[Connection, None, None]:
        conn_start = time.time()
        conn = self.engine.connect()
        conn_time = (time.time() - conn_start) * 1000
        logger.info(f"[DB] Connection acquired in {conn_time:.2f}ms")
        trans = conn.begin()
        try:
            yield conn
            trans.commit()
        except Exception:
            trans.rollback()
            raise
        finally:
            conn.close()

    def execute_query(
        self, query: Union[str, TextClause], params: Optional[Dict[str, Any]] = None
    ) -> Union[List[Dict[str, Any]], int]:
        try:
            with self.get_connection() as conn:
                query_start = time.time()
                result = conn.execute(query, params or {})
                query_time = (time.time() - query_start) * 1000
                if result.returns_rows:
                    columns = result.keys()
                    rows = result.fetchall()
                    result_data = [dict(zip(columns, row)) for row in rows]
                    logger.info(
                        f"[DB] Query executed in {query_time:.2f}ms, returned {len(result_data)} rows"
                    )
                    return result_data
                else:
                    logger.info(
                        f"[DB] Query executed in {query_time:.2f}ms, affected {result.rowcount} rows"
                    )
                    return result.rowcount
        except Exception as e:
            if "cached plan must not change result type" in str(e):
                logger.warning(
                    "Schema change detected, refreshing database connections..."
                )
                self.refresh_connections()
                with self.get_connection() as conn:
                    result = conn.execute(query, params or {})
                    if result.returns_rows:
                        columns = result.keys()
                        rows = result.fetchall()
                        return [dict(zip(columns, row)) for row in rows]
                    return result.rowcount
            else:
                raise

    def refresh_connections(self) -> None:
        logger.info("[DB] Refreshing connection pool")
        self.engine.dispose()


def read_postgres_table(table_name: str) -> pd.DataFrame:
    full_table_name = _get_full_table_name(table_name)
    logger.info(f"[DB] Reading data from PostgreSQL table: {full_table_name}")
    query = text(f"SELECT * FROM {full_table_name} ORDER BY compliance_id ASC")

    try:
        df = pd.read_sql(query, db.engine)

        logger.info(f"[DB] Successfully read {len(df)} rows from {full_table_name}")

        for col in df.select_dtypes(
            include=["datetime64[ns]", "datetime64[ns, UTC]"]
        ).columns:
            df[col] = df[col].dt.strftime("%Y-%m-%d").fillna("")

        return df
    except Exception as e:
        logger.error(f"[DB] Error reading from PostgreSQL: {e}")
        return pd.DataFrame()


def form_write_to_postgres(
    customer_name: str,
    equipment_model: str,
    service_date: str,
    issue_description: str,
    repair_status: str,
) -> int:
    logger.info("[DB] Attempting to write to PostgreSQL")
    full_table_name = _get_full_table_name("form_service_calls")
    query = text(
        f"""
        INSERT INTO {full_table_name} (customer_name, equipment_model, issue_description, repair_status, filed_at, created_at)
        VALUES (:customer_name, :equipment_model, :issue_description, :repair_status, :filed_at, :created_at)
    """
    )
    params = {
        "customer_name": customer_name,
        "equipment_model": equipment_model,
        "issue_description": issue_description,
        "repair_status": repair_status,
        "filed_at": service_date,
        "created_at": datetime.now(),
    }
    try:
        rowcount = db.execute_query(query, params)
        logger.info(f"[DB] Write to PostgreSQL query executed, rowcount: {rowcount}")
        if not isinstance(rowcount, int):
            logger.error(
                f"[DB] Expected int for rowcount, but got {type(rowcount).__name__}"
            )
            # Potentially raise an error or handle as per application logic
            return 0
        if rowcount == 0:
            logger.warning("[DB] Insert query affected 0 rows.")
        return rowcount
    except Exception as e:
        logger.error(f"[DB] Error writing to PostgreSQL: {e}")
        raise


def update_records_from_dataframe(
    df_updates: pd.DataFrame, table_name: str, pk_column: str
) -> int:
    full_table_name = _get_full_table_name(table_name)
    total_affected = 0

    update_cols = [col for col in df_updates.columns if col != pk_column]

    logger.info(f"[DB] Updating {len(df_updates)} records in {full_table_name}")

    try:
        for idx, row in df_updates.iterrows():
            set_clause = ", ".join([f'"{col}" = :{col}' for col in update_cols])

            query = text(f"""
                UPDATE {full_table_name}
                SET {set_clause}
                WHERE "{pk_column}" = :{pk_column}
            """)

            params = row.to_dict()

            result = db.execute_query(query, params)
            total_affected += result if isinstance(result, int) else 0

            if (idx + 1) % 100 == 0:
                logger.info(f"[DB] Processed {idx + 1}/{len(df_updates)} rows")

        logger.info(f"[DB] Update complete. {total_affected} rows affected.")
        return total_affected

    except Exception as e:
        logger.error(f"[DB] Error in batch update: {e}")
        raise


def dataframe_to_postgres(df: pd.DataFrame, table_name: str) -> int:
    try:
        full_table_name = _get_full_table_name(table_name)
        logger.info(
            f"[DB] Writing to schema: {db.schema or 'public'}, table: {table_name}"
        )

        with db.engine.begin() as conn:
            if not df.empty:
                # Check if table exists
                check_query = text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = :schema AND table_name = :table_name
                    )
                """)
                table_exists = conn.execute(
                    check_query, 
                    {"schema": db.schema or "public", "table_name": table_name}
                ).scalar()
                
                if table_exists:
                    # Get column types from existing table
                    col_types_query = text("""
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_schema = :schema AND table_name = :table_name
                    """)
                    col_types = conn.execute(
                        col_types_query,
                        {"schema": db.schema or "public", "table_name": table_name}
                    ).fetchall()
                    
                    # Convert date columns to datetime
                    for col_name, data_type in col_types:
                        if col_name in df.columns and data_type in ('date', 'timestamp'):
                            logger.info(f"[DB] Converting column '{col_name}' to datetime")
                            df[col_name] = pd.to_datetime(df[col_name], errors='coerce')
                    
                    # Clear existing data without dropping the table
                    logger.info(f"[DB] Deleting all rows from existing table {full_table_name}")
                    conn.execute(text(f"DELETE FROM {full_table_name}"))
                
                df.to_sql(
                    name=table_name,
                    con=conn,
                    schema=db.schema,
                    if_exists="append" if table_exists else "fail",
                    method="multi",
                    index=False,
                )
                logger.info(f"[DB] DataFrame successfully written to {full_table_name}")

        with db.engine.connect() as verify_conn:
            try:
                verify_query = text(f"SELECT COUNT(*) FROM {full_table_name}")
                count_result = verify_conn.execute(verify_query)
                row_count = count_result.scalar()
                logger.info(f"[DB] Verified {row_count} rows in {full_table_name}")
                return len(df)
            except Exception as e:
                logger.warning(f"[DB] Could not verify table {full_table_name}: {e}")
                return len(df)

    except Exception as e:
        logger.error(f"[DB] Error writing DataFrame to PostgreSQL: {e}")
        raise


db = Database()
