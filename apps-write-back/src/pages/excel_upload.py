import base64
import io
import logging
import os

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
import pandas as pd
from dash import Input, Output, State, callback, dcc, html
from dotenv import load_dotenv

from database_delta import dataframe_to_delta
from database_postgres import dataframe_to_postgres
from utilities import make_radiocard

load_dotenv()

logger = logging.getLogger(__name__)

dash.register_page(
    __name__,
    path="/excel_upload",
    name="Upload Excel file",
    icon="lucide:file",
    order=3,
)

DELTA_CATALOG = os.getenv("UNITY_CATALOG_CATALOG")
DELTA_SCHEMA = os.getenv("UNITY_CATALOG_SCHEMA")
POSTGRES_SCHEMA = os.getenv("POSTGRES_SCHEMA")


EXPECTED_SCHEMA = {
    "pricing_id": "object",
    "product_code": "object",
    "region": "object",
    "wholesale_price": "float64",
    "retail_price": "float64",
    "effective_from": "datetime64[ns]",
    "currency": "object",
    "price_type": "object",
}

EXPECTED_COLUMNS = list(EXPECTED_SCHEMA.keys())


def validate_schema(df):
    errors = []

    missing_cols = set(EXPECTED_COLUMNS) - set(df.columns)
    if missing_cols:
        errors.append(f"Missing columns: {', '.join(missing_cols)}")

    extra_cols = set(df.columns) - set(EXPECTED_COLUMNS)
    if extra_cols:
        errors.append(f"Unexpected columns: {', '.join(extra_cols)}")

    return errors


def parse_contents(contents, filename):
    content_type, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)

    try:
        if "xlsx" in filename or "xls" in filename:
            df = pd.read_excel(io.BytesIO(decoded))
        else:
            return None, ["Please upload an Excel file (.xlsx or .xls)"]

        if "effective_from" in df.columns:
            df["effective_from"] = pd.to_datetime(df["effective_from"], errors="coerce")

        schema_errors = validate_schema(df)

        return df, schema_errors
    except Exception as e:
        return None, [f"Error processing file: {str(e)}"]


def get_target_table_name(target):
    if target == "delta":
        return f"{DELTA_CATALOG}.{DELTA_SCHEMA}.excel_prices"
    if target == "postgresql":
        return f"{POSTGRES_SCHEMA}.excel_prices"
    return None


layout = html.Div(
    [
        html.Div(
            [
                dmc.Title("Upload Excel file", order=1),
                dcc.Markdown(
                    """
            Insert data into a **Delta table** or **PostgreSQL table** from an **Excel file**.
            """
                ),
            ]
        ),
        dmc.Title(
            "Target configuration",
            order=2,
            mb="md",
        ),
        dmc.RadioGroup(
            id="upload-target-radio",
            label="Upload target",
            description="Select the target table to write to",
            style={"maxWidth": "600px", "margin": "20px 0"},
            value="delta",
            children=[
                make_radiocard(
                    label="Delta table",
                    value="delta",
                    description=f"{DELTA_CATALOG}.{DELTA_SCHEMA}.excel_prices",
                ),
                make_radiocard(
                    label="PostgreSQL table",
                    value="postgresql",
                    description=f"{POSTGRES_SCHEMA}.excel_prices",
                ),
            ],
        ),
        dmc.Text(
            f"Expected columns: {', '.join(EXPECTED_COLUMNS)}",
            size="lg",
            fw=500,
        ),
        dmc.Title("Select Excel file", order=2, mt="md", mb="md"),
        html.A(
            dmc.Button("Download example Excel file", variant="outline"),
            href="/assets/example_excel.xlsx",
            download="example_excel.xlsx",
            style={"display": "block", "marginBottom": "1rem"},
        ),
        dcc.Upload(
            id="upload-data",
            children=dmc.Paper(
                [
                    dmc.Stack(
                        [
                            dmc.Text("Drag and Drop or "),
                            dmc.Button("Select file", variant="outline", w="133px"),
                        ],
                        gap="md",
                        align="center",
                    )
                ],
                shadow="sm",
                radius="md",
                p="xl",
                withBorder=True,
                style={
                    "margin": "20px 0",
                    "textAlign": "center",
                    "cursor": "pointer",
                },
            ),
            multiple=False,
        ),
        html.Div(id="upload-status"),
        html.Div(id="file-info"),
        html.Div(id="data-preview"),
        html.Div(id="import-section"),
        dcc.Store(id="uploaded-data"),
    ],
    style={"padding": "20px"},
)


@callback(
    [
        Output("uploaded-data", "data"),
        Output("upload-status", "children"),
        Output("file-info", "children"),
        Output("data-preview", "children"),
        Output("import-section", "children"),
    ],
    Input("upload-data", "contents"),
    State("upload-data", "filename"),
    State("upload-target-radio", "value"),
)
def update_output(contents, filename, target):
    if contents is None:
        return None, None, None, None, None

    df, errors = parse_contents(contents, filename)

    if errors:
        status = dmc.Alert(
            title="Upload Error",
            children=[dmc.Text(error) for error in errors],
            color="red",
            mb="md",
        )
        return None, status, None, None, None

    if "effective_from" in df.columns:
        df["effective_from"] = df["effective_from"].dt.strftime("%Y-%m-%d")

    status = dmc.Alert(
        title="Upload Successful",
        children="File uploaded and validated successfully!",
        color="green",
        mb="md",
    )

    info = dmc.Card(
        [
            dmc.Text(f"File: {filename}", size="lg", fw=500),
            dmc.Text(f"Rows: {len(df)}", size="md"),
            dmc.Text(f"Columns: {len(df.columns)}", size="md"),
        ],
        p="md",
        mb="md",
    )

    preview = html.Div(
        [
            dmc.Title("File preview", order=3, mb="md"),
            dag.AgGrid(
                id="data-grid",
                rowData=df.head(100).to_dict("records"),
                columnDefs=[
                    {"field": col, "sortable": True, "filter": True}
                    for col in df.columns
                ],
                style={"height": "400px"},
                dashGridOptions={
                    "pagination": True,
                    "paginationPageSize": 20,
                    "defaultColDef": {
                        "resizable": True,
                        "sortable": True,
                        "filter": True,
                    },
                },
            ),
        ]
    )

    table_name = get_target_table_name(target)
    import_section = dmc.Card(
        [
            dmc.Title("Import Data", order=3, mb="md"),
            dmc.Text(f"Ready to import {len(df)} rows to {table_name}", mb="md"),
            dmc.Button(
                "Import data",
                id="import-button",
                color="lava",
                size="lg",
            ),
            html.Div(id="import-status", style={"marginTop": "1rem"}),
        ],
        p="md",
        mt="md",
    )

    return df.to_dict("records"), status, info, preview, import_section


@callback(
    Output("import-status", "children"),
    Input("import-button", "n_clicks"),
    State("uploaded-data", "data"),
    State("upload-target-radio", "value"),
    prevent_initial_call=True,
    running=[
        (Output("import-button", "disabled"), True, False),
        (Output("import-button", "loading"), True, False),
    ],
)
def import_data(n_clicks, data, target):
    if not data:
        return dmc.Alert(
            "No data to import.", title="Error", color="red", withCloseButton=True
        )

    df = pd.DataFrame(data)

    try:
        if target == "delta":
            dataframe_to_delta(df)
            table_name = f"{DELTA_CATALOG}.{DELTA_SCHEMA}.excel_prices"
        elif target == "postgresql":
            dataframe_to_postgres(df, "excel_prices")
            table_name = f"{POSTGRES_SCHEMA}.excel_prices"
        else:
            return dmc.Alert(
                "Invalid target selected.",
                title="Error",
                color="red",
                withCloseButton=True,
            )

        return dmc.Alert(
            f"Successfully imported {len(df)} rows to {table_name}",
            title="Success",
            color="green",
            withCloseButton=True,
        )
    except Exception as e:
        logger.error(f"Error importing data to {target}: {e}")
        return dmc.Alert(
            f"Failed to import data: {e}",
            title="Import Error",
            color="red",
            withCloseButton=True,
        )
