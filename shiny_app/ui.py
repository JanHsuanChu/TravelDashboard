# ui.py
# Travel Dashboard — mockup-aligned layout (nav, single Plan card, outputs grid).

from pathlib import Path

from shiny import ui

from components import (
    compare_with_rows_content,
    destination_fields_content,
    dining_output_ui,
    essential_info_ui,
    food_preference_combined_content,
    travel_friendliness_ui,
    when_fields_content,
)
from travel_friendliness.country_names_data import load_wb_country_names

APP_ROOT = Path(__file__).resolve().parent

_INTER_FONT = ui.tags.link(
    rel="stylesheet",
    href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
)

# Debounced email for server preload + device UUID for future UX (see docs/ui_flow_preferences.md)
_PREF_CLIENT_JS = ui.tags.script(
    """
    (function() {
      var tdEmailTimer = null;
      function ensureDeviceId() {
        try {
          var k = 'td_device_id';
          var v = window.localStorage.getItem(k);
          if (!v) {
            v = (window.crypto && crypto.randomUUID)
              ? crypto.randomUUID()
              : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                  var r = Math.random() * 16 | 0, x = c === 'x' ? r : (r & 0x3 | 0x8);
                  return x.toString(16);
                });
            window.localStorage.setItem(k, v);
          }
          return v;
        } catch (e) { return ''; }
      }
      function pushDebouncedEmail(val) {
        if (window.Shiny && window.Shiny.setInputValue) {
          Shiny.setInputValue('user_email_debounced', val, { priority: 'event' });
        }
      }
      function scheduleDebouncedEmail(val) {
        if (tdEmailTimer) clearTimeout(tdEmailTimer);
        tdEmailTimer = setTimeout(function() {
          tdEmailTimer = null;
          pushDebouncedEmail(val);
        }, 500);
      }
      function flushDebouncedEmailFromField() {
        var el = document.getElementById('user_email');
        if (el) pushDebouncedEmail(el.value);
      }
      function pushDeviceId() {
        var id = ensureDeviceId();
        if (id && window.Shiny && window.Shiny.setInputValue) {
          Shiny.setInputValue('device_id', id, { priority: 'event' });
        }
      }
      function onSessionReady() {
        pushDeviceId();
        flushDebouncedEmailFromField();
      }
      // Delegation: works even if #user_email is not in the DOM when this script runs.
      document.addEventListener('input', function(ev) {
        var t = ev.target;
        if (!t || t.id !== 'user_email') return;
        scheduleDebouncedEmail(t.value);
      });
      document.addEventListener('focusout', function(ev) {
        var t = ev.target;
        if (!t || t.id !== 'user_email') return;
        if (tdEmailTimer) clearTimeout(tdEmailTimer);
        tdEmailTimer = null;
        pushDebouncedEmail(t.value);
      });
      document.addEventListener('shiny:connected', onSessionReady);
      window.addEventListener('shiny:connected', onSessionReady);
    })();
    """
)

_TD_COUNTRY_DATALIST_JS = ui.tags.script(
    """
    (function() {
      function attachWbCountryDatalist() {
        ['dest_country', 'cmp1_country', 'cmp2_country'].forEach(function(id) {
          var el = document.getElementById(id);
          if (el) el.setAttribute('list', 'td_wb_country_datalist');
        });
      }
      document.addEventListener('shiny:connected', attachWbCountryDatalist);
      window.addEventListener('shiny:connected', attachWbCountryDatalist);
    })();
    """
)


def _wb_country_datalist_ui():
    names = load_wb_country_names()
    if not names:
        return ui.div()
    return ui.tags.datalist(
        *[ui.tags.option(value=n) for n in names],
        id="td_wb_country_datalist",
    )


app_ui = ui.page_fillable(
    ui.head_content(
        _INTER_FONT,
        ui.include_css(APP_ROOT / "www" / "custom.css"),
        _PREF_CLIENT_JS,
        _TD_COUNTRY_DATALIST_JS,
    ),
    ui.div(_wb_country_datalist_ui(), class_="td-wb-datalist-host"),
    ui.div(
        ui.div(
            ui.div(
                ui.span("T", class_="td-nav-logo"),
                ui.span("Travel Dashboard", class_="td-nav-title"),
                class_="td-nav-brand",
            ),
            ui.div(
                ui.tags.a("Preferences", href="#plan", class_="td-nav-link"),
                ui.span(class_="td-nav-avatar"),
                class_="td-nav-links",
            ),
            class_="td-nav",
        ),
        ui.div(
            ui.div(
                ui.card(
                    ui.div(
                        ui.h2("Plan Your Trip", class_="td-plan-title"),
                        ui.p(
                            "Enter your destination and preferences to generate a personalized itinerary.",
                            class_="td-plan-sub",
                        ),
                        class_="td-plan-header",
                    ),
                    ui.layout_columns(
                        destination_fields_content(),
                        compare_with_rows_content(),
                        when_fields_content(),
                        col_widths=(4, 4, 4),
                    ),
                    ui.div(
                        food_preference_combined_content(),
                        class_="td-plan-food-row",
                    ),
                    ui.div(
                        ui.div(
                            ui.input_text("user_email_debounced", None, value=""),
                            class_="td-hidden-shiny-input-wrap",
                        ),
                        ui.div(
                            ui.input_text("device_id", None, value=""),
                            class_="td-hidden-shiny-input-wrap",
                        ),
                        ui.layout_columns(
                            ui.div(
                                ui.input_text(
                                    "user_first_name",
                                    "First name",
                                    placeholder="Ada",
                                    autocomplete="section-td-identity given-name",
                                ),
                                ui.p(
                                    "Add your first name and email to save preferences for future visits.",
                                    class_="td-muted td-identity-hint",
                                ),
                                class_="td-identity-col",
                            ),
                            ui.div(
                                ui.input_text(
                                    "user_email",
                                    "Email",
                                    placeholder="ada@example.com",
                                    autocomplete="section-td-identity email",
                                ),
                                ui.p(
                                    "We use your email to remember your preferences on this device.",
                                    class_="td-muted td-identity-hint",
                                ),
                                ui.p(ui.output_text("last_saved_hint"), class_="td-muted td-last-saved"),
                                class_="td-identity-col",
                            ),
                            ui.div(
                                ui.input_action_button(
                                    "btn_save",
                                    "Save food preferences",
                                    class_="btn td-btn-secondary",
                                ),
                                ui.input_action_button(
                                    "btn_generate",
                                    "Generate recommendations",
                                    class_="btn td-btn-primary-mockup",
                                ),
                                class_="td-action-row td-actions-end",
                            ),
                            col_widths=(4, 4, 4),
                        ),
                        class_="td-plan-row3",
                    ),
                    id="plan",
                    class_="td-card td-plan-card",
                ),
                ui.h4("Outputs", class_="td-section-title"),
                ui.div(
                    ui.layout_columns(
                        dining_output_ui(),
                        essential_info_ui(),
                        travel_friendliness_ui(),
                        col_widths=(4, 4, 4),
                    ),
                    class_="td-out-grid",
                ),
                class_="td-shell",
            ),
            class_="td-page-inner",
        ),
        class_="td-page-root",
    ),
    title="Travel Dashboard",
    padding="0",
    gap="0",
    class_="td-page",
)
