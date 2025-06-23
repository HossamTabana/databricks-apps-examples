import os

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html
from dotenv import load_dotenv

from database_delta import form_write_to_delta
from database_postgres import form_write_to_postgres
from utilities import make_radiocard

load_dotenv()

dash.register_page(
    __name__, path="/", name="Fill out form", icon="lucide:file-text", order=1
)

DELTA_CATALOG = os.getenv("UNITY_CATALOG_CATALOG")
DELTA_SCHEMA = os.getenv("UNITY_CATALOG_SCHEMA")
POSTGRES_SCHEMA = os.getenv("POSTGRES_SCHEMA")

COMMON_FORM_STYLE = {"maxWidth": "600px", "margin": "20px 0"}

layout = html.Div(
    [
        html.Div(
            [
                dmc.Title("Form data entry", order=1),
                dcc.Markdown(
                    """
            Insert data into a **Delta table** or a **PostgreSQL table** using a form.
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
            id="form-table-type-radio",
            label="Table type",
            description="Select the target table to write to",
            style=COMMON_FORM_STYLE,
            value="delta",
            children=[
                make_radiocard(
                    label="Delta table",
                    value="delta",
                    description=f"{DELTA_CATALOG}.{DELTA_SCHEMA}.form_service_calls",
                ),
                make_radiocard(
                    label="PostgreSQL table",
                    value="postgresql",
                    description=f"{POSTGRES_SCHEMA}.form_service_calls",
                ),
            ],
        ),
        dmc.Title(
            "Sample form",
            order=2,
            mb="md",
        ),
        dmc.Paper(
            [
                dmc.Title("Service call form", order=3, mb="md"),
                dmc.Stack(
                    [
                        dmc.TextInput(
                            label="Customer name",
                            id="customer-name",
                            placeholder="Enter customer name",
                            required=True,
                        ),
                        dmc.TextInput(
                            label="Equipment model",
                            id="equipment-model",
                            placeholder="Enter equipment model",
                            required=True,
                        ),
                        dmc.DatePickerInput(
                            label="Service date",
                            id="service-date",
                            placeholder="Select service date",
                            required=True,
                            value=None,
                            w="100%",
                        ),
                        dmc.Textarea(
                            label="Issue description",
                            id="issue-description",
                            placeholder="Describe the issue in detail",
                            required=True,
                            minRows=4,
                            autosize=True,
                        ),
                        dmc.Select(
                            label="Repair status",
                            id="repair-status",
                            placeholder="Select repair status",
                            required=True,
                            data=[
                                {"value": "pending", "label": "Pending"},
                                {"value": "completed", "label": "Completed"},
                                {"value": "parts_needed", "label": "Parts Needed"},
                            ],
                        ),
                        dmc.Group(
                            [
                                dmc.Button(
                                    "Submit",
                                    id="submit-button",
                                    variant="filled",
                                    color="lava",
                                ),
                                dmc.Button(
                                    "Clear",
                                    id="clear-button",
                                    variant="light",
                                    color="gray",
                                ),
                            ],
                            justify="flex-end",
                            mt="lg",
                        ),
                    ],
                    gap="md",
                ),
            ],
            shadow="sm",
            radius="sm",
            p="xl",
            withBorder=True,
            style=COMMON_FORM_STYLE,
        ),
    ],
    style={"padding": "20px"},
)


@callback(
    Output("notification-container", "sendNotifications"),
    Input("submit-button", "n_clicks"),
    State("form-table-type-radio", "value"),
    State("customer-name", "value"),
    State("equipment-model", "value"),
    State("service-date", "value"),
    State("issue-description", "value"),
    State("repair-status", "value"),
    prevent_initial_call=True,
    running=[
        (Output("submit-button", "disabled"), True, False),
        (Output("submit-button", "loading"), True, False),
    ],
)
def submit_form(
    n_clicks,
    table_type,
    customer_name,
    equipment_model,
    service_date,
    issue_description,
    repair_status,
):
    # Only proceed if the button was actually clicked
    if not n_clicks or n_clicks == 0:
        return dash.no_update
    
    # Validate required fields
    if not all([customer_name, equipment_model, service_date, issue_description, repair_status]):
        return [
            {
                "action": "show",
                "title": "Validation Error",
                "message": "Please fill in all required fields before submitting.",
                "color": "red",
            }
        ]

    db_operations = {
        "delta": {"func": form_write_to_delta, "name": "Delta table"},
        "postgresql": {"func": form_write_to_postgres, "name": "PostgreSQL table"},
    }

    operation = db_operations.get(table_type)

    if not operation:
        return dash.no_update

    try:
        operation["func"](
            customer_name,
            equipment_model,
            service_date,
            issue_description,
            repair_status,
        )
        return [
            {
                "action": "show",
                "title": "Success!",
                "message": f"Successfully wrote to {operation['name']}.",
                "color": "green",
            }
        ]
    except Exception as e:
        return [
            {
                "action": "show",
                "title": "Error!",
                "message": f"Error writing to {operation['name']}: {e}",
                "color": "red",
            }
        ]


@callback(
    Output("customer-name", "value"),
    Output("equipment-model", "value"),
    Output("service-date", "value"),
    Output("issue-description", "value"),
    Output("repair-status", "value"),
    Input("clear-button", "n_clicks"),
    prevent_initial_call=True,
)
def clear_form(n_clicks):
    if not n_clicks or n_clicks == 0:
        return dash.no_update
    return "", "", None, "", None
