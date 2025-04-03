import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, dash_table
from .functions import get_connection, read_table

dash.register_page(
    module=__name__,
    name="Read a table",
    path="/tables/read",
    category="tables",
)

layout = dmc.Stack(
    children=[
        dmc.Title("Read a table", order=1),
        dmc.TextInput(
            id="table-name",
            label="Table name",
            description="Enter a table name to read from",
            value="samples.nyctaxi.trips",
            w=500,
            styles={"wrapper": {"font-family": "monospace"}},
        ),
        dmc.Button("Run query", id="run-query", variant="outline"),
        dash_table.DataTable(
            id="table-output",
            style_table={"marginTop": "20px", "width": "100%"},
            style_header={
                "backgroundColor": "#EEEDE9",
                "fontWeight": "bold",
            },
            style_cell={
                "textAlign": "left",
                "padding": "12px",
                "fontFamily": "DM Sans",
            },
            style_data={
                "whiteSpace": "normal",
                "height": "auto",
            },
            style_data_conditional=[
                {
                    "if": {"row_index": "odd"},
                    "backgroundColor": "#F9F7F4",
                }
            ],
            page_size=25,
            sort_action="native",
        ),
    ],
    align="flex-start",
    gap="md",
    style={"padding": "20px"},
)


@callback(
    Output("table-output", "data"),
    Output("table-output", "columns"),
    Input("run-query", "n_clicks"),
    Input("table-name", "value"),
)
def read_table_callback(n_clicks, table_name):
    if not n_clicks:
        return [], []

    try:
        conn = get_connection()
        df = read_table(table_name, conn)

        data = df.to_dict("records")

        columns = [{"name": col, "id": col, "deletable": False} for col in df.columns]

        return data, columns
    except Exception as e:
        return [], []
