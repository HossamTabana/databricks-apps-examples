import logging

import dash_mantine_components as dmc
from dash import Dash, dcc, get_asset_url, html, page_container, page_registry
from dash_iconify import DashIconify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_icon(icon):
    return DashIconify(icon=icon, height=16)


app = Dash(
    __name__,
    external_stylesheets=dmc.styles.ALL,
    use_pages=True,
    pages_folder="pages",
    suppress_callback_exceptions=True,
)

layout = dmc.AppShell(
    [
        dmc.AppShellHeader(children=[]),
        dmc.AppShellNavbar(
            id="navbar",
            children=[
                html.Div(
                    dcc.Link(
                        children=[
                            html.Img(
                                src=get_asset_url("logo.svg"),
                                style={"height": 30},
                            ),
                        ],
                        href="/",
                    ),
                    style={
                        "display": "flex",
                        "justify-content": "flex-start",
                        "width": "100%",
                        "margin-top": "1.5rem",
                        "margin-bottom": "1.5rem",
                        "margin-left": "12px",
                    },
                ),
            ]
            + [
                dmc.NavLink(
                    label=page["name"],
                    leftSection=get_icon(icon=page.get("icon", "lucide:table")),
                    href=page["relative_path"],
                    active="partial",
                )
                for page in page_registry.values()
            ],
            p="lg",
            style={"background-color": "#EEEDE9"},
        ),
        dmc.AppShellMain(
            id="main", children=page_container, style={"background-color": "#F9F7F4"}
        ),
    ],
    header={"collapsed": True},
    padding="lg",
    navbar={
        "width": 300,
        "breakpoint": "sm",
        "collapsed": {"mobile": True},
    },
    id="appshell",
)


app.layout = dmc.MantineProvider(
    theme={
        "fontFamily": "DM Sans",
        "colors": {
            "lava": [
                "#ffe9e6",
                "#ffd2cd",
                "#ffa49a",
                "#ff7264",
                "#ff4936",
                "#ff2e18",
                "#ff1e07",
                "#e40f00",
                "#cc0500",
                "#b20000",
            ]
        },
        "primaryColor": "lava",
    },
    children=[
        dcc.Location(id="url"),
        dmc.NotificationContainer(id="notification-container"),
        layout,
    ],
)

if __name__ == "__main__":
    app.run(debug=True)
