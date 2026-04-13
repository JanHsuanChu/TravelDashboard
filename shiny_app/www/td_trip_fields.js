/**
 * Strict country combobox (Fuse.js): type to search, pick from list, ISO2 in hidden input.
 */
(function () {
  var countries = [];
  var countryFlat = [];
  var fuse = null;
  var MAX_SUG = 8;
  var selected = { dest: null, cmp1: null, cmp2: null };

  function fetchCountriesJson() {
    return fetch("/data/countries_slim.json", { credentials: "same-origin" })
      .then(function (r) {
        if (r.ok) return r.json();
        throw new Error("bad status");
      })
      .catch(function () {
        return fetch("data/countries_slim.json", { credentials: "same-origin" }).then(function (r2) {
          if (r2.ok) return r2.json();
          throw new Error("fallback failed");
        });
      });
  }

  function getCountriesPayload() {
    var emb = window.__TD_COUNTRIES_SLIM__;
    if (emb && emb.countries && emb.countries.length) {
      return Promise.resolve(emb);
    }
    return fetchCountriesJson();
  }

  function suppressBrowserAutofill(el) {
    if (!el || el.getAttribute("data-td-no-chrome-address") === "1") return;
    el.setAttribute("data-td-no-chrome-address", "1");
    el.setAttribute("autocomplete", "new-password");
    el.setAttribute("autocorrect", "off");
    el.setAttribute("autocapitalize", "off");
    el.setAttribute("spellcheck", "false");
    el.setAttribute("data-lpignore", "true");
    el.setAttribute("data-1p-ignore", "true");
    el.setAttribute("data-bwignore", "true");
    el.setAttribute("data-form-type", "other");
    el.setAttribute("name", "td-trip-field-" + el.id);
  }

  function simpleCountrySearch(q, flat, maxN) {
    var ql = (q || "").toLowerCase();
    if (!ql) return [];
    var out = [];
    for (var i = 0; i < flat.length && out.length < maxN; i++) {
      var it = flat[i];
      if (!it || !it.cca2) continue;
      if (
        it.searchText.indexOf(ql) !== -1 ||
        (it.name && it.name.toLowerCase().indexOf(ql) !== -1) ||
        (it.cca2 && it.cca2.toLowerCase().indexOf(ql) !== -1)
      ) {
        out.push(it);
      }
    }
    return out;
  }

  var _fuseWaitAttempts = 0;
  var MAX_FUSE_WAIT = 160;

  function loadFuse(cb) {
    if (typeof Fuse === "undefined") {
      _fuseWaitAttempts += 1;
      if (_fuseWaitAttempts < MAX_FUSE_WAIT) {
        setTimeout(function () {
          loadFuse(cb);
        }, 50);
        return;
      }
    }
    getCountriesPayload()
      .then(function (data) {
        countries = data.countries || [];
        countryFlat = countries.map(function (c) {
          var parts = []
            .concat(c.aliases || [])
            .concat([c.name, c.cca2])
            .filter(Boolean);
          var searchText = parts.join(" ").toLowerCase();
          return { cca2: c.cca2, name: c.name, searchText: searchText };
        });
        if (typeof Fuse !== "undefined" && countryFlat.length) {
          fuse = new Fuse(countryFlat, {
            keys: ["searchText", "name", "cca2"],
            threshold: 0.34,
            ignoreLocation: true,
            minMatchCharLength: 1,
          });
        } else {
          fuse = null;
        }
        cb();
      })
      .catch(function () {
        countries = [];
        countryFlat = [];
        fuse = null;
        cb();
      });
  }

  function setShiny(id, val) {
    if (window.Shiny && window.Shiny.setInputValue) {
      window.Shiny.setInputValue(id, val, { priority: "event" });
    }
  }

  function hideDropdown(ul) {
    if (ul) {
      ul.style.display = "none";
      ul.innerHTML = "";
    }
  }

  function showDropdown(input, ul, items) {
    if (!ul) return;
    ul.innerHTML = "";
    items.forEach(function (it) {
      var li = document.createElement("li");
      li.textContent = it.name + " (" + it.cca2 + ")";
      li.setAttribute("data-cca2", it.cca2);
      li.setAttribute("data-name", it.name);
      li.className = "td-country-dd-item";
      ul.appendChild(li);
    });
    ul.style.display = items.length ? "block" : "none";
  }

  function bindCountryField(prefix) {
    var id = prefix + "_country";
    var input = document.getElementById(id);
    if (!input) return;
    suppressBrowserAutofill(input);
    var ul = document.getElementById(id + "_dd");
    if (!ul) {
      ul = document.createElement("ul");
      ul.id = id + "_dd";
      ul.className = "td-country-dd";
      ul.setAttribute("role", "listbox");
      var wrap = input.closest(".form-group") || input.parentNode;
      if (wrap) {
        wrap.classList.add("td-country-combo");
        wrap.style.position = "relative";
        wrap.appendChild(ul);
      }
    }

    function pickItem(name, cca2) {
      selected[prefix] = { name: name, cca2: cca2 };
      input.value = name;
      setShiny(prefix + "_country", name);
      setShiny(prefix + "_country_iso2", cca2);
      var hid = document.getElementById(prefix + "_country_iso2");
      if (hid) hid.value = cca2;
      hideDropdown(ul);
    }

    input.addEventListener("input", function () {
      selected[prefix] = null;
      setShiny(prefix + "_country_iso2", "");
      var q = input.value.trim();
      if (q.length < 1) {
        hideDropdown(ul);
        return;
      }
      var items;
      if (fuse) {
        items = fuse
          .search(q)
          .slice(0, MAX_SUG)
          .map(function (r) {
            return r.item;
          })
          .filter(function (x) {
            return x && x.cca2;
          });
      } else {
        items = simpleCountrySearch(q, countryFlat, MAX_SUG);
      }
      showDropdown(input, ul, items);
    });

    input.addEventListener("blur", function () {
      setTimeout(function () {
        var sel = selected[prefix];
        if (sel && sel.cca2) {
          hideDropdown(ul);
          return;
        }
        var isoEl = document.getElementById(prefix + "_country_iso2");
        var iso = isoEl ? isoEl.value : "";
        if (!iso || !iso.trim()) {
          input.value = "";
          setShiny(prefix + "_country", "");
          setShiny(prefix + "_country_iso2", "");
          selected[prefix] = null;
        }
        hideDropdown(ul);
      }, 200);
    });

    ul.addEventListener("mousedown", function (ev) {
      var li = ev.target.closest(".td-country-dd-item");
      if (!li) return;
      ev.preventDefault();
      var name = li.getAttribute("data-name") || "";
      var cca2 = li.getAttribute("data-cca2") || "";
      if (name && cca2) pickItem(name, cca2);
    });
  }

  function bindCityField(prefix) {
    var city = document.getElementById(prefix + "_city");
    if (!city) return;
    suppressBrowserAutofill(city);
  }

  var _tdTripFieldsInitDone = false;

  function runTripFieldsBind() {
    if (_tdTripFieldsInitDone) return;
    if (!document.getElementById("dest_country")) return;
    if (!window.Shiny || !window.Shiny.setInputValue) return;
    loadFuse(function () {
      ["dest", "cmp1", "cmp2"].forEach(bindCountryField);
      ["dest", "cmp1", "cmp2"].forEach(bindCityField);
      _tdTripFieldsInitDone = true;
    });
  }

  function scheduleTripFieldsInit() {
    var tries = 0;
    function tick() {
      if (_tdTripFieldsInitDone) return;
      var el = document.getElementById("dest_country");
      var shinyOk = window.Shiny && window.Shiny.setInputValue;
      if (el && shinyOk) {
        runTripFieldsBind();
        return;
      }
      tries += 1;
      if (tries < 400) setTimeout(tick, 50);
    }
    tick();
  }

  document.addEventListener("shiny:connected", scheduleTripFieldsInit);
  window.addEventListener("shiny:connected", scheduleTripFieldsInit);
  document.addEventListener("DOMContentLoaded", scheduleTripFieldsInit);
  scheduleTripFieldsInit();
})();
