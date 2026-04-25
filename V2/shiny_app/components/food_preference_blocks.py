from shiny import ui

import shiny_app.tags as tagdata
import shiny_app.validators as val


def food_preference_combined_content():
    """Full-width row: three columns (like / dislike / dietary), tags + text per column."""
    return ui.div(
        ui.div(
            ui.p("Food preferences", class_="td-input-label td-food-row-title"),
            ui.p(
                "Recommendations are powered by Google Maps reviews.",
                class_="td-dining-maps-disclaimer",
            ),
            class_="td-food-preferences-header-with-note",
        ),
        ui.layout_columns(
            ui.div(
                ui.span("Food I like", class_="td-food-mini-head"),
                ui.input_checkbox_group(
                    "like_tags",
                    None,
                    choices=tagdata.FOOD_LIKE_CHOICES,
                    inline=True,
                ),
                ui.input_text_area(
                    "food_like_text",
                    "More detail (optional)",
                    rows=2,
                    placeholder="Anything else you enjoy…",
                ),
                class_="td-food-stack-item td-food-stack-like",
            ),
            ui.div(
                ui.span("Food I dislike", class_="td-food-mini-head"),
                ui.input_checkbox_group(
                    "dislike_tags",
                    None,
                    choices=tagdata.FOOD_DISLIKE_CHOICES,
                    inline=True,
                ),
                ui.input_text_area(
                    "food_dislike_text",
                    "More detail (optional)",
                    rows=2,
                    placeholder="Other foods to avoid…",
                ),
                class_="td-food-stack-item td-food-stack-dislike",
            ),
            ui.div(
                ui.span("Dietary restrictions", class_="td-food-mini-head"),
                ui.input_checkbox_group(
                    "dietary_tags",
                    None,
                    choices=tagdata.DIETARY_CHOICES,
                    inline=True,
                ),
                ui.input_text_area(
                    "dietary_restrictions_text",
                    "Allergies or other restrictions (optional)",
                    rows=2,
                    placeholder="Allergies or other restrictions…",
                ),
                class_="td-food-stack-item td-food-stack-dietary",
            ),
            col_widths=(4, 4, 4),
        ),
        class_="td-input-group td-food-combined",
    )


def food_preference_blocks_ui():
    return ui.card(
        ui.card_header("Food preferences"),
        ui.p(
            f"Preset tags plus open text (max {val.MAX_WORDS_FOOD_TEXT} words per text box).",
            class_="td-muted",
        ),
        ui.layout_columns(
            ui.div(
                ui.h6("Food I like"),
                ui.input_checkbox_group(
                    "like_tags",
                    None,
                    choices=tagdata.FOOD_LIKE_CHOICES,
                ),
                ui.input_text_area(
                    "food_like_text",
                    "More detail (optional)",
                    rows=2,
                    placeholder="Anything else you enjoy…",
                ),
            ),
            ui.div(
                ui.h6("Food I dislike"),
                ui.input_checkbox_group(
                    "dislike_tags",
                    None,
                    choices=tagdata.FOOD_DISLIKE_CHOICES,
                ),
                ui.input_text_area(
                    "food_dislike_text",
                    "More detail (optional)",
                    rows=2,
                    placeholder="Other foods to avoid…",
                ),
            ),
            ui.div(
                ui.h6("Dietary restrictions"),
                ui.input_checkbox_group(
                    "dietary_tags",
                    None,
                    choices=tagdata.DIETARY_CHOICES,
                ),
                ui.input_text_area(
                    "dietary_restrictions_text",
                    "Allergies or other restrictions (optional)",
                    rows=2,
                    placeholder="Allergies or other restrictions…",
                ),
            ),
            col_widths=(4, 4, 4),
        ),
        class_="td-card td-food-card",
    )
