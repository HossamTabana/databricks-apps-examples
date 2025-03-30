import os
from databricks import sql
from databricks.sdk.core import Config

DATABRICKS_SQL_WAREHOUSE_ID = os.getenv("DATABRICKS_SQL_WAREHOUSE_ID")

cfg = Config()


def get_connection():
    return sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{DATABRICKS_SQL_WAREHOUSE_ID}",
        credentials_provider=lambda: cfg.authenticate,
    )


def read_table(table_name, conn):
    with conn.cursor() as cursor:
        query = f"SELECT * FROM {table_name} LIMIT 100"
        cursor.execute(query)
        df = cursor.fetchall_arrow().to_pandas()
        print(df)
        return df
