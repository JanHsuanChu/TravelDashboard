# ui.py
# Composes Travel Dashboard layout (mockup-aligned; Bootstrap-style cards via Shiny ui.card).

from pathlib import Path

from shiny import ui

from components import (
    compare_with_rows_ui,
    destination_fields_ui,
    dining_output_ui,
    essential_info_ui,
    food_preference_blocks_ui,
    travel_friendliness_ui,
    when_fields_ui,
)

APP_ROOT = Path(__file__).resolve().parent

app_ui = ui.page_fillable(
    ui.head_content(ui.include_css(APP_ROOT / "www" / "custom.css")),
    ui.div(
        ui.h1("Travel Dashboard", class_="td-title"),
        ui.p("Plan trips, preferences, and recommendations.", class_="td-subtitle"),
        class_="td-hero",
    ),
    ui.layout_columns(
        destination_fields_ui(),
        compare_with_rows_ui(),
        when_fields_ui(),
        col_widths=(4, 4, 4),
    ),
    food_preference_blocks_ui(),
    ui.card(
        ui.card_header("Profile & actions"),
        ui.layout_columns(
            ui.input_text("user_first_name", "First name", placeholder="Ada"),
            ui.input_text("user_email", "Email", placeholder="ada@example.com"),
            col_widths=(6, 6),
        ),
        ui.div(
            ui.input_action_button(
                "btn_save",
                "Save food preferences",
                class_="btn td-btn-primary",
            ),
            ui.input_action_button(
                "btn_generate",
                "Generate recommendations",
                class_="btn td-btn-accent",
            ),
            class_="td-action-row",
        ),
        class_="td-card",
    ),
    ui.h4("Recent preferences (Supabase)"),
    ui.output_table("prefs_table"),
    ui.p(ui.output_text("load_status"), class_="td-muted"),
    ui.h4("Outputs"),
    ui.layout_columns(
        dining_output_ui(),
        essential_info_ui(),
        travel_friendliness_ui(),
        col_widths=(4, 4, 4),
    ),
    title="Travel Dashboard",
    padding="1rem 1.5rem",
    gap="1rem",
    class_="td-page",
)
