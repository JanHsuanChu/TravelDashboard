from shiny import ui


def compare_with_rows_ui():
    return ui.card(
        ui.card_header("Compare with (optional)"),
        ui.p("Two rows · country + optional city each", class_="td-muted"),
        ui.layout_columns(
            ui.p("1", class_="td-row-num"),
            ui.input_text("cmp1_country", "Country", placeholder="Country"),
            ui.input_text("cmp1_city", "City (optional)", placeholder="City"),
            col_widths=(1, 5, 6),
        ),
        ui.layout_columns(
            ui.p("2", class_="td-row-num"),
            ui.input_text("cmp2_country", "Country", placeholder="Country"),
            ui.input_text("cmp2_city", "City (optional)", placeholder="City"),
            col_widths=(1, 5, 6),
        ),
        class_="td-card",
    )
