from shiny import ui


def essential_info_ui():
    return ui.card(
        ui.card_header("Essential info"),
        ui.output_ui("out_essential"),
        class_="td-card td-out-card",
        height="100%",
    )
