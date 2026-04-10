# UI component fragments for Travel Dashboard Shiny app.

from .compare_with_rows import compare_with_rows_content, compare_with_rows_ui
from .destination_fields import destination_fields_content, destination_fields_ui
from .dining_output_card import dining_output_ui
from .essential_info_card import essential_info_ui
from .food_preference_blocks import food_preference_blocks_ui, food_preference_combined_content
from .travel_friendliness_card import travel_friendliness_ui
from .when_fields import when_fields_content, when_fields_ui

__all__ = [
    "compare_with_rows_content",
    "compare_with_rows_ui",
    "destination_fields_content",
    "destination_fields_ui",
    "dining_output_ui",
    "essential_info_ui",
    "food_preference_blocks_ui",
    "food_preference_combined_content",
    "travel_friendliness_ui",
    "when_fields_content",
    "when_fields_ui",
]
