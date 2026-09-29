import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../custom_components/mojelektro/frontend/mojelektro-energy-card.js", import.meta.url), "utf8");
const elements = new Map();
const context = {
  window: {},
  customElements: {
    get: (key) => elements.get(key),
    define: (key, value) => elements.set(key, value),
  },
  HTMLElement: class {
    attachShadow() {
      this.shadowRoot = { innerHTML: "", querySelector: () => null };
      return this.shadowRoot;
    }
    get isConnected() { return true; }
  },
  Date, Number, Map, Set, Array, String, Intl,
};
const instrumented = source.replace(
  "  if (!customElements.get(CARD))",
  "  window.testHelpers = { finiteState, resolveEntities, historyDays, escapeHtml };\n  if (!customElements.get(CARD))",
);
assert.notEqual(instrumented, source);
runInNewContext(instrumented, context);
const { finiteState, resolveEntities, historyDays, escapeHtml } = context.window.testHelpers;

test("card is optional and registered with the Home Assistant picker", () => {
  assert.ok(elements.has("mojelektro-energy-card"));
  assert.equal(context.window.customCards[0].type, "mojelektro-energy-card");
});

test("empty, unavailable and nonfinite readings never become zero", () => {
  for (const state of ["", "unknown", "unavailable", "NaN", "Infinity"]) {
    assert.equal(finiteState({ state }), null);
  }
  assert.equal(finiteState({ state: "0" }), 0);
  assert.equal(finiteState({ state: "4.65" }), 4.65);
});

test("meter selection uses unique IDs even after entity IDs are renamed", () => {
  const entries = [
    { platform: "mojelektro", unique_id: "4-111-sensor.mojelektro_daily_input", entity_id: "sensor.house_import" },
    { platform: "mojelektro", unique_id: "4-111-button.mojelektro_refresh_data", entity_id: "button.house_refresh" },
    { platform: "mojelektro", unique_id: "4-222-sensor.mojelektro_daily_input", entity_id: "sensor.garage_import" },
    { platform: "mojelektro", unique_id: "4-222-sensor.mojelektro_total_input", entity_id: "sensor.garage_total", disabled_by: "user" },
    { platform: "other", unique_id: "4-111-sensor.mojelektro_total_input", entity_id: "sensor.unrelated" },
  ];
  assert.equal(resolveEntities(entries, null), null);
  assert.equal(resolveEntities(entries, "4-111").daily_input, "sensor.house_import");
  assert.equal(resolveEntities(entries, "4-111").refresh_data, "button.house_refresh");
  assert.equal(resolveEntities(entries, "4-222").total_input, undefined);
  assert.equal(resolveEntities(entries, "unknown"), null);
});

test("history keeps the newest finite recorded value per change date", () => {
  const start = Date.parse("2026-09-01T00:00:00Z");
  const end = Date.parse("2026-09-04T00:00:00Z");
  const rows = historyDays([[
    { state: "9", last_changed: "2026-08-31T20:00:00Z" },
    { state: "7", last_changed: "2026-09-02T06:00:00Z" },
    { state: "unavailable", last_changed: "2026-09-02T07:00:00Z" },
    { state: "4.65", last_changed: "2026-09-02T08:00:00Z" },
    { state: "3", last_changed: "2026-09-03T08:00:00Z" },
  ]], start, end);
  assert.deepEqual(Array.from(rows, (row) => row.value), [4.65, 3]);
  assert.deepEqual(Array.from(historyDays(null, start, end)), []);
});

test("dashboard title is escaped before being inserted in HTML", () => {
  assert.equal(escapeHtml('<img src=x onerror="x">'), "&lt;img src=x onerror=&quot;x&quot;&gt;");
});

test("card renders live entity values and keeps missing readings blank", () => {
  const Card = elements.get("mojelektro-energy-card");
  const card = new Card();
  card.setConfig({ title: "Hi <script>alert(1)</script>" });
  card._entities = {
    daily_input: "sensor.renamed_daily",
    total_input: "sensor.renamed_total",
    last_published_reading: "sensor.last_reading",
  };
  card._hass = {
    language: "sl",
    states: {
      "sensor.renamed_daily": { state: "4.65" },
      "sensor.renamed_total": { state: "unavailable" },
      "sensor.last_reading": { state: "2026-09-22T06:00:00+02:00" },
    },
  };
  card._render();
  assert.match(card.shadowRoot.innerHTML, /Zadnji dnevni odjem/);
  assert.match(card.shadowRoot.innerHTML, /4,65/);
  assert.match(card.shadowRoot.innerHTML, /Skupni odjem<\/span><strong>—/);
  assert.match(card.shadowRoot.innerHTML, /Hi &lt;script&gt;/);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /<script>/);
});
