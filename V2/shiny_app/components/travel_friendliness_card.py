from shiny import ui


def travel_friendliness_ui():
    return ui.card(
        ui.card_header("Travel friendliness"),
        ui.div(
            ui.div(ui.output_ui("out_friendliness"), class_="td-out-scroll"),
            ui.div(ui.output_ui("friendliness_download_area"), class_="td-friendliness-actions"),
            class_="td-friendliness-panel",
        ),
        class_="td-card td-out-card td-out-accent-friendliness",
        height="100%",
    )
