from shiny import ui

import tags as tagdata
import validators as val


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
