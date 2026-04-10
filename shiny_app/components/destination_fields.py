from shiny import ui


def destination_fields_content():
    """Inputs only (no card) — for Plan Your Trip grid."""
    return ui.div(
        ui.p("Where I am going", class_="td-input-label td-trip-section-title"),
        ui.p("Country required · city optional · pick from suggestions as you type", class_="td-muted td-input-hint"),
        ui.layout_columns(
            ui.input_text(
                "dest_country",
                "Country",
                placeholder="e.g. Japan — use suggestion list",
                autocomplete="section-td-trip td-destination-country",
            ),
            ui.input_text(
                "dest_city",
                "City (optional)",
                placeholder="e.g. Kyoto",
                autocomplete="section-td-trip td-destination-city",
            ),
            col_widths=(6, 6),
        ),
        class_="td-input-group",
    )


def destination_fields_ui():
    return ui.card(
        ui.card_header("Where I am going"),
        ui.p("Country required · city optional", class_="td-muted"),
        ui.layout_columns(
            ui.input_text(
                "dest_country",
                "Country",
                placeholder="e.g. Japan",
                autocomplete="section-td-trip td-destination-country",
            ),
            ui.input_text(
                "dest_city",
                "City (optional)",
                placeholder="e.g. Kyoto",
                autocomplete="section-td-trip td-destination-city",
            ),
            col_widths=(6, 6),
        ),
        class_="td-card",
    )
