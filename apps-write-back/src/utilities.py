import dash_mantine_components as dmc


def make_radiocard(label, value, description):
    return dmc.RadioCard(
        value=value,
        withBorder=True,
        p="md",
        mt="md",
        bg="white",
        children=[
            dmc.Group(
                [
                    dmc.RadioIndicator(),
                    dmc.Box(
                        [
                            dmc.Text(label, lh="1.3", fz="md", fw="bold"),
                            dmc.Text(description, size="sm", c="dimmed"),
                        ]
                    ),
                ],
                wrap="nowrap",
                align="flex-start",
            )
        ],
    )
