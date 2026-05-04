# ui.py
# Travel Dashboard — mockup-aligned layout (nav, single Plan card, outputs grid).

import json
from pathlib import Path

from shiny import ui

from shiny_app.components import (
    compare_with_rows_content,
    destination_fields_content,
    dining_dishes_output_ui,
    dining_places_map_output_ui,
    essential_info_ui,
    food_preference_combined_content,
    travel_friendliness_ui,
    when_fields_content,
)
APP_ROOT = Path(__file__).resolve().parent

# Inline RestCountries-derived list for Fuse (avoids fetch failures if /data/ is blocked or mis-routed).
_COUNTRIES_SLIM_PATH = APP_ROOT / "www" / "data" / "countries_slim.json"
_TD_COUNTRIES_EMBED_JS = ui.tags.script(
    "window.__TD_COUNTRIES_SLIM__ = "
    + json.dumps(json.loads(_COUNTRIES_SLIM_PATH.read_text(encoding="utf-8")), ensure_ascii=False)
    + ";"
)

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

_MAP_PLACE_ROW_CLICK_JS = ui.tags.script(
    """
    document.addEventListener('click', function(ev) {
      var row = ev.target.closest('[data-td-place-idx]');
      if (!row || !window.Shiny || !window.Shiny.setInputValue) return;
      if (ev.target.closest('a')) return;
      var idx = row.getAttribute('data-td-place-idx');
      if (idx === null || idx === '') return;
      Shiny.setInputValue('map_place_pick', idx, { priority: 'event' });
    });
    """
)

_AGENT_CHIP_CLICK_JS = ui.tags.script(
    """
    document.addEventListener('click', function(ev) {
      var chip = ev.target.closest('[data-td-agent-chip]');
      if (!chip || !window.Shiny || !window.Shiny.setInputValue) return;
      var msg = chip.getAttribute('data-td-agent-chip');
      if (!msg) return;
      Shiny.setInputValue('agent_quick_reply', msg, { priority: 'event' });
    });
    """
)

_CHAT_WIDGET_JS = ui.tags.script(
    """
    (function() {
      function qs(sel){ return document.querySelector(sel); }
      function qsa(sel){ return document.querySelectorAll(sel); }
      function scrollChatToBottom(){
        var box = qs('#td-chat-widget .td-chat-messages');
        if (!box) return;
        box.scrollTop = box.scrollHeight;
      }
      function scheduleScrollBurst(){
        var delays = [0, 40, 120, 260, 420];
        for (var i = 0; i < delays.length; i++) {
          (function(d){ setTimeout(scrollChatToBottom, d); })(delays[i]);
        }
      }
      function openWidget(){
        var el = qs('#td-chat-widget');
        if (!el) return;
        el.classList.add('td-chat-widget-open');
        scheduleScrollBurst();
      }
      function closeWidget(){
        var el = qs('#td-chat-widget');
        if (!el) return;
        el.classList.remove('td-chat-widget-open');
      }
      var chatObserver = null;
      var rootObserver = null;
      function ensureChatObserver(){
        var root = qs('#td-chat-widget');
        if (!root || !window.MutationObserver) return;
        if (chatObserver) { try { chatObserver.disconnect(); } catch(e) {} chatObserver = null; }
        chatObserver = new MutationObserver(function(muts){
          for (var i = 0; i < muts.length; i++) {
            var m = muts[i];
            if (m.type === 'childList') {
              var t = m.target;
              if (t && (t.classList && t.classList.contains('td-chat-messages') || (t.closest && t.closest('.td-chat-messages')))) {
                scheduleScrollBurst();
                break;
              }
            }
          }
        });
        chatObserver.observe(root, { childList: true, subtree: true });
      }
      function ensureRootObserver(){
        if (rootObserver || !window.MutationObserver) return;
        rootObserver = new MutationObserver(function(){
          ensureChatObserver();
          scheduleScrollBurst();
        });
        rootObserver.observe(document.body, { childList: true, subtree: true });
      }
      document.addEventListener('click', function(ev){
        var t = ev.target;
        if (!t) return;
        if (t.closest('#td-chat-close')) { ev.preventDefault(); closeWidget(); return; }
        if (t.closest('#td-chat-fab')) {
          ev.preventDefault();
          var el = qs('#td-chat-widget');
          if (!el) return;
          if (el.classList.contains('td-chat-widget-open')) closeWidget(); else openWidget();
          return;
        }
        if (t.closest('#btn_generate')) { setTimeout(openWidget, 50); return; }
        if (t.closest('#btn_agent_send') || t.closest('[data-td-agent-chip]')) {
          scheduleScrollBurst();
          return;
        }
      });
      document.addEventListener('shiny:value', function(){ ensureChatObserver(); scheduleScrollBurst(); });
      document.addEventListener('shiny:connected', function(){ ensureRootObserver(); ensureChatObserver(); scheduleScrollBurst(); });
      window.addEventListener('load', function(){ ensureRootObserver(); ensureChatObserver(); scheduleScrollBurst(); });
    })();
    """
)

_CHAT_INPUT_ENTER_JS = ui.tags.script(
    """
    document.addEventListener('keydown', function(ev) {
      var t = ev.target;
      if (!t || t.id !== 'agent_chat_input') return;
      if (ev.key !== 'Enter') return;
      if (ev.isComposing || ev.keyCode === 229) return;
      if (ev.shiftKey) return;
      ev.preventDefault();
      var btn = document.getElementById('btn_agent_send');
      if (btn) btn.click();
    });
    """
)

# Bundled Fuse (CDN can be blocked; must load before td_trip_fields.js).
_FUSE_JS = ui.include_js(path=APP_ROOT / "www" / "vendor" / "fuse.min.js")
_TRIP_FIELDS_JS = ui.include_js(path=APP_ROOT / "www" / "td_trip_fields.js")


app_ui = ui.page_fillable(
    ui.head_content(
        _INTER_FONT,
        ui.include_css(APP_ROOT / "www" / "custom.css"),
        _MAP_PLACE_ROW_CLICK_JS,
        _AGENT_CHIP_CLICK_JS,
        _CHAT_WIDGET_JS,
        _CHAT_INPUT_ENTER_JS,
        _PREF_CLIENT_JS,
        _TD_COUNTRIES_EMBED_JS,
        _FUSE_JS,
        _TRIP_FIELDS_JS,
    ),
        ui.div(
            ui.output_ui("plan_card_visibility_style"),
            ui.output_ui("new_location_bar"),
            ui.div(
                ui.div(
                    ui.span("T", class_="td-nav-logo"),
                    ui.span("Travel Dashboard", class_="td-nav-title"),
                    class_="td-nav-brand",
                ),
                class_="td-nav",
            ),
            ui.div(
            ui.div(
                ui.card(
                    ui.div(
                        ui.h2("Plan Your Trip", class_="td-plan-title"),
                        ui.p(
                            "Enter your destination and preferences to generate a personalized recommendation.",
                            class_="td-plan-sub",
                        ),
                        class_="td-plan-header",
                    ),
                    ui.div(),
                    ui.layout_columns(
                        destination_fields_content(),
                        compare_with_rows_content(),
                        when_fields_content(),
                        col_widths=(4, 4, 4),
                    ),
                    ui.div(
                        ui.p(
                            "Optional — name and email save your food preferences for next visits. "
                            "Return with the same email and we load your last saved selections.",
                            class_="td-muted td-identity-intro",
                        ),
                        ui.div(
                            ui.input_text("user_email_debounced", None, value=""),
                            class_="td-hidden-shiny-input-wrap",
                        ),
                        ui.div(
                            ui.input_text("device_id", None, value=""),
                            class_="td-hidden-shiny-input-wrap",
                        ),
                        ui.div(
                            ui.layout_columns(
                                ui.div(
                                    ui.input_text(
                                        "user_first_name",
                                        "First name",
                                        placeholder="Ada",
                                        autocomplete="section-td-identity given-name",
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
                                    ui.p(ui.output_text("last_saved_hint"), class_="td-muted td-last-saved"),
                                    class_="td-identity-col",
                                ),
                                ui.div(
                                    ui.input_action_button(
                                        "btn_save",
                                        "Save food preferences",
                                        class_="btn btn-sm td-btn-secondary td-identity-action-btn",
                                    ),
                                    class_="td-action-row td-actions-end td-plan-identity-actions",
                                ),
                                col_widths=(4, 4, 4),
                            ),
                            class_="td-plan-identity-row",
                        ),
                        class_="td-plan-identity-block",
                    ),
                    ui.div(
                        ui.output_ui("food_section_ui"),
                        class_="td-plan-food-row",
                    ),
                    ui.div(
                        ui.input_action_button(
                            "btn_generate",
                            "Generate recommendations",
                            class_="btn td-btn-primary-mockup td-generate-recommendations-btn",
                        ),
                        class_="td-generate-after-food",
                    ),
                    id="plan",
                    class_="td-card td-plan-card",
                ),
                ui.h4("Outputs", class_="td-section-title"),
                ui.div(
                    ui.layout_columns(
                        dining_dishes_output_ui(),
                        essential_info_ui(),
                        travel_friendliness_ui(),
                        col_widths=(4, 4, 4),
                    ),
                    class_="td-out-grid",
                ),
                ui.div(
                    dining_places_map_output_ui(),
                    class_="td-dining-places-row",
                ),
                class_="td-shell",
            ),
            ui.div(
                ui.output_ui("chat_area_ui"),
                id="td-chat-widget",
                class_="td-chat-widget",
            ),
            ui.div(
                ui.output_ui("qc_widget_ui"),
                id="td-qc-widget-root",
                class_="td-qc-widget-root",
            ),
            ui.tags.button(
                ui.span("Food guide", class_="td-chat-fab-label"),
                type="button",
                id="td-chat-fab",
                class_="td-chat-fab",
                **{"aria-label": "Open Food guide chat"},
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
