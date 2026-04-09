from shiny import ui


def destination_fields_ui():
    return ui.card(
        ui.card_header("Where I am going"),
        ui.p("Country required · city optional", class_="td-muted"),
        ui.layout_columns(
            ui.input_text("dest_country", "Country", placeholder="e.g. Japan"),
            ui.input_text("dest_city", "City (optional)", placeholder="e.g. Kyoto"),
            col_widths=(6, 6),
        ),
        class_="td-card",
    )
