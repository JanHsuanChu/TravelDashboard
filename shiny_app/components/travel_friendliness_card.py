from shiny import ui


def travel_friendliness_ui():
    return ui.card(
        ui.card_header("Travel friendliness"),
        ui.output_ui("out_friendliness"),
        class_="td-card td-out-card",
        height="100%",
    )
