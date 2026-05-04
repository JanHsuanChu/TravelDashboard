from shiny import ui


def essential_info_ui():
    return ui.card(
        ui.card_header("Essential info"),
        ui.div(
            ui.div(ui.output_ui("out_essential")),
            ui.div(ui.output_ui("out_destination_news")),
            class_="td-out-scroll td-essential-body",
        ),
        class_="td-card td-out-card td-out-accent-essential",
        height="100%",
    )
