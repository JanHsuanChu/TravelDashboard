from shiny import ui


def dining_output_ui():
    return ui.card(
        ui.card_header("Dining recommendations"),
        ui.div(ui.output_ui("out_dining"), class_="td-out-scroll"),
        class_="td-card td-out-card td-out-accent-dining",
        height="100%",
    )
