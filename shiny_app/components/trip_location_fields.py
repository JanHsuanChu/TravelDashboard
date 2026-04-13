"""Trip country (strict ISO2 + label) and city rows with hint/chip output slots."""

from __future__ import annotations

from shiny import ui


def _hidden_iso2(input_id: str) -> ui.Tag:
    return ui.div(
        ui.input_text(input_id, None, value=""),
        class_="td-hidden-shiny-input-wrap",
    )


def destination_block():
    """Where I am going: chip + country + city + hint rows."""
    return ui.div(
        ui.p("Where I am going", class_="td-input-label td-trip-section-title"),
        ui.layout_columns(
            ui.div(
                ui.input_text(
                    "dest_country",
                    "Country",
                    placeholder="Type to search, then pick from list",
                    autocomplete="new-password",
                    spellcheck="false",
                ),
                _hidden_iso2("dest_country_iso2"),
                class_="td-country-combo",
            ),
            ui.div(
                ui.input_text(
                    "dest_city",
                    "City or region (optional)",
                    placeholder="e.g. Kyoto or Tuscany",
                    autocomplete="new-password",
                    spellcheck="false",
                ),
                class_="td-city-field-col",
            ),
            col_widths=(6, 6),
        ),
        class_="td-input-group",
    )


def compare_block():
    """Compare with: two rows of country + city."""
    return ui.div(
        ui.p("Compare with (optional)", class_="td-input-label td-trip-section-title"),
        ui.layout_columns(
            ui.div(
                ui.input_text(
                    "cmp1_country",
                    "Country",
                    placeholder="Type to search, then pick from list",
                    autocomplete="new-password",
                    spellcheck="false",
                ),
                _hidden_iso2("cmp1_country_iso2"),
                class_="td-country-combo",
            ),
            ui.div(
                ui.input_text(
                    "cmp1_city",
                    "City or region (optional)",
                    placeholder="e.g. Paris",
                    autocomplete="new-password",
                    spellcheck="false",
                ),
                class_="td-city-field-col",
            ),
            col_widths=(6, 6),
        ),
        ui.layout_columns(
            ui.div(
                ui.input_text(
                    "cmp2_country",
                    "Country",
                    placeholder="Type to search, then pick from list",
                    autocomplete="new-password",
                    spellcheck="false",
                ),
                _hidden_iso2("cmp2_country_iso2"),
                class_="td-country-combo",
            ),
            ui.div(
                ui.input_text(
                    "cmp2_city",
                    "City or region (optional)",
                    placeholder="e.g. Rome",
                    autocomplete="new-password",
                    spellcheck="false",
                ),
                class_="td-city-field-col",
            ),
            col_widths=(6, 6),
        ),
        class_="td-input-group td-compare-block",
    )
