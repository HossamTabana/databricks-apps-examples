import logging
import os

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
import pandas as pd
from dash import Input, Output, State, callback, dcc, html
from dash_iconify import DashIconify
from dotenv import load_dotenv

import database_delta as db
import database_postgres as db_pg
from utilities import make_radiocard

load_dotenv()

logger = logging.getLogger(__name__)

dash.register_page(
    __name__, path="/edit-table", name="Edit a table", icon="lucide:table", order=2
)

DELTA_CATALOG = os.getenv("UNITY_CATALOG_CATALOG")
DELTA_SCHEMA = os.getenv("UNITY_CATALOG_SCHEMA")
POSTGRES_SCHEMA = os.getenv("POSTGRES_SCHEMA")


DATA_SOURCES = {
    "delta": {
        "label": "Delta table",
        "title": "Delta Lake table",
        "table_name": "table_regional_compliance",
        "display_name": f"{DELTA_CATALOG}.{DELTA_SCHEMA}.table_regional_compliance",
        "read_func": db.read_delta_table,
        "update_func": lambda df, table_name: db.update_delta_records(
            df_updates=df, table_name=table_name, pk_column="compliance_id"
        ),
    },
    "postgres": {
        "label": "PostgreSQL table",
        "title": "PostgreSQL table",
        "table_name": "table_regional_compliance",
        "display_name": f"{POSTGRES_SCHEMA}.table_regional_compliance",
        "read_func": db_pg.read_postgres_table,
        "update_func": lambda df, table_name: db_pg.update_records_from_dataframe(
            df_updates=df, table_name=table_name, pk_column="compliance_id"
        ),
    },
}


def load_source_data(source_name, config):
    table_name = config["table_name"]
    if not table_name:
        logger.warning(f"table_name not configured for {source_name}")
        return pd.DataFrame()
    try:
        return config["read_func"](table_name)
    except Exception as e:
        logger.error(f"Could not load {source_name} data from {table_name}: {e}")
        return pd.DataFrame()


def create_column_defs(df):
    if df.empty:
        return []
    defs = [{"field": i} for i in df.columns]
    for col_def in defs:
        if col_def["field"] == "compliance_id":
            col_def["editable"] = False
    return defs


def create_table_panel(source_name, config, data, column_defs):
    table_name = config.get("display_name", "Not configured")
    return dmc.TabsPanel(
        value=source_name,
        children=[
            dmc.Title(config["title"], order=2, mt="md", mb="md"),
            dmc.Text(f"Table: {table_name}", size="sm", c="dimmed", mb="sm"),
            dcc.Loading(
                dag.AgGrid(
                    id={"type": "grid", "name": source_name},
                    rowData=data,
                    columnDefs=column_defs,
                    columnSize="sizeToFit",
                    defaultColDef={"editable": True, "filter": True, "sortable": True},
                    dashGridOptions={
                        "editType": "fullRow",
                        "undoRedoCellEditing": True,
                        "undoRedoCellEditingLimit": 20,
                        "rowSelection": "multiple",
                    },
                    className="ag-theme-alpine",
                ),
                type="circle",
                color="red",
            ),
            html.Div(
                id={"type": "summary", "name": source_name}, style={"margin": "20px 0"}
            ),
            dmc.Button(
                "Update records",
                id={"type": "save-button", "name": source_name},
                n_clicks=0,
                style={"margin-top": "10px", "margin-bottom": "10px"},
            ),
        ],
    )


def layout():
    return html.Div(
        [
            dcc.Store(id="initial-load-trigger"),
            html.Div(id="table-edit-notification-container"),
            *[
                dcc.Store(id={"type": "notification-store", "name": name})
                for name in DATA_SOURCES
            ],
            *[
                dcc.Store(id={"type": "original-data", "name": name}, data=[])
                for name in DATA_SOURCES
            ],
            *[
                dcc.Store(id={"type": "changes", "name": name}, data={})
                for name in DATA_SOURCES
            ],
            *[
                dcc.Store(id={"type": "refresh-trigger", "name": name}, data=0)
                for name in DATA_SOURCES
            ],
            dmc.Title("Edit a table", order=1),
            dcc.Markdown(
                "Edit and update a **Delta table** or a **PostgreSQL table** using a data grid."
            ),
            dmc.Title("Target configuration", order=2, mb="md"),
            dmc.RadioGroup(
                id="edit-table-type-radio",
                label="Table type",
                description="Select the target table to write to",
                style={"maxWidth": "600px", "margin": "20px 0"},
                value="delta",
                children=[
                    make_radiocard(
                        label=config["label"],
                        value=name,
                        description=config.get("display_name"),
                    )
                    for name, config in DATA_SOURCES.items()
                ],
            ),
            dmc.Tabs(
                id="edit-tabs",
                value="delta",
                children=[
                    dmc.TabsList(
                        [
                            dmc.TabsTab(config["label"], value=name)
                            for name, config in DATA_SOURCES.items()
                        ],
                        style={"display": "none"},
                    ),
                    *[
                        create_table_panel(
                            name,
                            config,
                            [],
                            [],
                        )
                        for name, config in DATA_SOURCES.items()
                    ],
                ],
            ),
        ],
        style={"padding": "20px"},
    )


@callback(
    Output({"type": "grid", "name": "delta"}, "rowData"),
    Output({"type": "grid", "name": "delta"}, "columnDefs"),
    Output({"type": "original-data", "name": "delta"}, "data"),
    Input("initial-load-trigger", "data"),
)
def load_delta_data(_):
    df = load_source_data("delta", DATA_SOURCES["delta"])
    if df.empty:
        return [], [], []
    data = df.to_dict("records")
    col_defs = create_column_defs(df)
    return data, col_defs, data


@callback(
    Output({"type": "grid", "name": "postgres"}, "rowData"),
    Output({"type": "grid", "name": "postgres"}, "columnDefs"),
    Output({"type": "original-data", "name": "postgres"}, "data"),
    Input("initial-load-trigger", "data"),
)
def load_postgres_data(_):
    df = load_source_data("postgres", DATA_SOURCES["postgres"])
    if df.empty:
        return [], [], []
    data = df.to_dict("records")
    col_defs = create_column_defs(df)
    return data, col_defs, data


@callback(
    Output("edit-tabs", "value"),
    Input("edit-table-type-radio", "value"),
)
def update_active_tab(table_type):
    return table_type


@callback(
    Output({"type": "summary", "name": dash.MATCH}, "children"),
    Output({"type": "changes", "name": dash.MATCH}, "data"),
    Input({"type": "grid", "name": dash.MATCH}, "cellValueChanged"),
    State({"type": "original-data", "name": dash.MATCH}, "data"),
    State({"type": "changes", "name": dash.MATCH}, "data"),
    prevent_initial_call=True,
)
def track_changes(cell_changed, original_data, current_changes):
    logger.info(f"cell_changed: {cell_changed}")
    logger.info(f"original_data length: {len(original_data)}")
    logger.info(f"current_changes: {current_changes}")

    if not cell_changed:
        logger.info("cell_changed is empty, no update.")
        return dash.no_update

    changes = current_changes.copy()
    list_of_changes = cell_changed if isinstance(cell_changed, list) else [cell_changed]
    logger.info(f"Processing {len(list_of_changes)} change events.")

    for i, change_event in enumerate(list_of_changes):
        logger.info(f"Processing change event {i + 1}: {change_event}")
        if not isinstance(change_event, dict):
            logger.warning(f"Change event {i + 1} is not a dict, skipping.")
            continue

        row_index = change_event.get("rowIndex")
        col_id = change_event.get("colId")
        new_value = change_event.get("value")
        logger.info(
            f"Change details: rowIndex={row_index}, colId='{col_id}', newValue='{new_value}'"
        )

        if row_index is None or col_id is None or row_index >= len(original_data):
            logger.warning(
                "Invalid change event data or rowIndex out of bounds, skipping."
            )
            continue

        original_row = original_data[row_index]
        compliance_id = original_row.get("compliance_id")
        if compliance_id is None:
            logger.warning("compliance_id not found in original row, skipping.")
            continue
        logger.info(f"Found compliance_id: {compliance_id}")

        row_key = str(compliance_id)

        original_value_for_comparison = (
            changes.get(row_key, {})
            .get(col_id, {})
            .get("original", original_row.get(col_id))
        )
        logger.info(f"Original value for comparison: '{original_value_for_comparison}'")

        if str(original_value_for_comparison) == str(new_value):
            logger.info("New value is same as original. Reverting change.")
            if row_key in changes and col_id in changes[row_key]:
                del changes[row_key][col_id]
                logger.info(f"Removed change for {row_key} -> {col_id}")
                if not changes[row_key]:
                    del changes[row_key]
                    logger.info(
                        f"Removed entry for {row_key} as it has no more changes."
                    )
        else:
            logger.info("New value is different from original. Storing change.")
            if row_key not in changes:
                changes[row_key] = {}
                logger.info(f"Created new entry for {row_key} in changes.")

            if col_id not in changes[row_key]:
                changes[row_key][col_id] = {
                    "original": original_row.get(col_id),
                    "current": new_value,
                }
                logger.info(f"Stored new change for {row_key} -> {col_id}")
            else:
                changes[row_key][col_id]["current"] = new_value
                logger.info(f"Updated current value for {row_key} -> {col_id}")

    logger.info(f"Final changes dict: {changes}")
    if not changes:
        logger.info("No changes to display in summary.")
        return "", {}

    # Rebuild the summary display from the self-contained 'changes' dictionary
    summary_items = []
    logger.info("Building summary display.")
    for pk, row_changes in changes.items():
        change_details = []
        for col, change_info in row_changes.items():
            original_val = change_info.get("original", "")
            current_val = change_info.get("current", "")

            change_details.append(
                dmc.Text(
                    [
                        dmc.Text(
                            f"{col.replace('_', ' ').capitalize()}: ", fw=500, span=True
                        ),
                        dmc.Text(
                            f"'{original_val}'",
                            c="red",
                            span=True,
                            style={"text-decoration": "line-through"},
                        ),
                        dmc.Text(" → ", span=True),
                        dmc.Text(f"'{current_val}'", c="green", span=True, fw=500),
                    ],
                    size="sm",
                )
            )

        if change_details:
            summary_items.append(
                dmc.Paper(
                    [
                        dmc.Text(f"Compliance ID: {pk}", fw=500, size="sm", mb="xs"),
                        html.Div(change_details, style={"padding-left": "10px"}),
                    ],
                    p="sm",
                    withBorder=True,
                    mb="xs",
                )
            )

    logger.info(f"Number of summary items created: {len(summary_items)}")
    summary_display = (
        dmc.Stack(
            [
                dmc.Text("Pending changes:", fw=600, size="md", c="blue"),
                dmc.Stack(summary_items, gap="xs"),
            ]
        )
        if summary_items
        else ""
    )
    logger.info(f"Summary display created. Is empty: {summary_display == ''}")

    return summary_display, changes


@callback(
    Output({"type": "notification-store", "name": dash.MATCH}, "data"),
    Output({"type": "refresh-trigger", "name": dash.MATCH}, "data"),
    Output({"type": "summary", "name": dash.MATCH}, "children", allow_duplicate=True),
    Output({"type": "changes", "name": dash.MATCH}, "data", allow_duplicate=True),
    Input({"type": "save-button", "name": dash.MATCH}, "n_clicks"),
    State({"type": "changes", "name": dash.MATCH}, "data"),
    State({"type": "grid", "name": dash.MATCH}, "rowData"),
    State({"type": "refresh-trigger", "name": dash.MATCH}, "data"),
    prevent_initial_call=True,
    running=[
        (Output({"type": "save-button", "name": dash.MATCH}, "loading"), True, False),
    ],
)
def save_changes(n_clicks, changes, grid_data, refresh_trigger_value):
    if n_clicks == 0 or not changes:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    source_name = dash.callback_context.triggered_id["name"]
    config = DATA_SOURCES[source_name]
    table_name = config["table_name"]

    try:
        changed_pks = {str(pk) for pk in changes.keys()}
        pk_column = "compliance_id"

        update_records = [
            row for row in grid_data if str(row.get(pk_column)) in changed_pks
        ]

        if not update_records:
            logger.warning("No records to update after filtering.")
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        df_updates = pd.DataFrame(update_records)

        config["update_func"](df_updates, table_name)

        notification = {
            "title": "Success",
            "message": "Data saved successfully!",
            "color": "green",
        }

        return notification, refresh_trigger_value + 1, "", {}

    except Exception as e:
        logger.error(f"Error saving changes to {source_name}: {e}")
        notification = {
            "title": "Error",
            "message": f"An error occurred: {e}",
            "color": "red",
        }
        return (
            notification,
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )


@callback(
    Output({"type": "grid", "name": dash.MATCH}, "rowData", allow_duplicate=True),
    Output({"type": "original-data", "name": dash.MATCH}, "data", allow_duplicate=True),
    Input({"type": "refresh-trigger", "name": dash.MATCH}, "data"),
    prevent_initial_call=True,
)
def refresh_grid_data(trigger):
    source_name = dash.callback_context.triggered_id["name"]
    config = DATA_SOURCES[source_name]

    df = load_source_data(source_name, config)
    if df.empty:
        return [], []
    data = df.to_dict("records")
    return data, data


@callback(
    Output("table-edit-notification-container", "children"),
    Input({"type": "notification-store", "name": dash.ALL}, "data"),
    prevent_initial_call=True,
)
def display_notification(notifications):
    ctx = dash.callback_context
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return dash.no_update

    notification_data = ctx.triggered[0]["value"]

    icon = (
        "ic:round-check-circle"
        if notification_data.get("color") == "green"
        else "ic:round-error"
    )

    return dmc.Notification(
        title=notification_data.get("title"),
        id="save-notification",
        action="show",
        message=notification_data.get("message"),
        color=notification_data.get("color"),
        icon=DashIconify(icon=icon),
        autoClose=5000,
    )
