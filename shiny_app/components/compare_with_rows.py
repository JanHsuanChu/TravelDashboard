from shiny import ui


def compare_with_rows_content():
    """Compact compare rows without index column."""
    return ui.div(
        ui.p("Compare with (optional)", class_="td-input-label td-trip-section-title"),
        ui.p("Two destinations · country + optional city each · suggestions as you type", class_="td-muted td-input-hint"),
        ui.layout_columns(
            ui.input_text(
                "cmp1_country",
                "Country",
                placeholder="e.g. France — pick from list",
                autocomplete="section-td-compare1 td-compare-country",
            ),
            ui.input_text(
                "cmp1_city",
                "City (optional)",
                placeholder="e.g. Paris",
                autocomplete="section-td-compare1 td-compare-city",
            ),
            col_widths=(6, 6),
        ),
        ui.layout_columns(
            ui.input_text(
                "cmp2_country",
                "Country",
                placeholder="e.g. Italy — pick from list",
                autocomplete="section-td-compare2 td-compare-country",
            ),
            ui.input_text(
                "cmp2_city",
                "City (optional)",
                placeholder="e.g. Rome",
                autocomplete="section-td-compare2 td-compare-city",
            ),
            col_widths=(6, 6),
        ),
        class_="td-input-group td-compare-block",
    )


def compare_with_rows_ui():
    return ui.card(
        ui.card_header("Compare with (optional)"),
        ui.p("Two rows · country + optional city each", class_="td-muted"),
        ui.layout_columns(
            ui.p("1", class_="td-row-num"),
            ui.input_text(
                "cmp1_country",
                "Country",
                placeholder="e.g. France",
                autocomplete="section-td-compare1 td-compare-country",
            ),
            ui.input_text(
                "cmp1_city",
                "City (optional)",
                placeholder="e.g. Paris",
                autocomplete="section-td-compare1 td-compare-city",
            ),
            col_widths=(1, 5, 6),
        ),
        ui.layout_columns(
            ui.p("2", class_="td-row-num"),
            ui.input_text(
                "cmp2_country",
                "Country",
                placeholder="e.g. Italy",
                autocomplete="section-td-compare2 td-compare-country",
            ),
            ui.input_text(
                "cmp2_city",
                "City (optional)",
                placeholder="e.g. Rome",
                autocomplete="section-td-compare2 td-compare-city",
            ),
            col_widths=(1, 5, 6),
        ),
        class_="td-card",
    )
