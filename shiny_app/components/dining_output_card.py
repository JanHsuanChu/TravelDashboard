from shiny import ui


def dining_output_ui():
    return ui.card(
        ui.card_header("Dining recommendations"),
        ui.output_ui("out_dining"),
        class_="td-card td-out-card",
        height="100%",
    )
