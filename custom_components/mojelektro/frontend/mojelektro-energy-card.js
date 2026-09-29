/* Optional Lovelace overview for the Moj Elektro integration. No token or API calls. */
(() => {
  "use strict";

  const CARD = "mojelektro-energy-card";
  const KEYS = [
    "15min_input", "15min_output", "daily_input", "daily_output",
    "daily_input_peak", "daily_input_offpeak", "monthly_input",
    "monthly_output", "monthly_input_peak", "monthly_input_offpeak",
    "total_input", "total_output", "last_published_reading",
    ...Array.from({ length: 5 }, (_, i) => `daily_input_blok_${i + 1}`),
    ...Array.from({ length: 5 }, (_, i) => `casovni_blok_${i + 1}`),
    "data_stale", "refresh_data",
  ];
  const LABELS = {
    sl: {
      title: "Moj Elektro", subtitle: "Pregled energije", daily: "Zadnji dnevni odjem",
      monthly: "Mesečni odjem", total: "Skupni odjem", quarter: "Zadnjih 15 minut",
      output: "Oddaja v omrežje", net: "Neto dnevni odjem", tariffs: "Tarifi v tem mesecu",
      dailyOutput: "Zadnja dnevna oddaja", totalOutput: "Skupna oddaja",
      cost: "Ocena mesečnega stroška energije", costInfo: "Samo energija; brez omrežnine, prispevkov in davkov.",
      peak: "Višja tarifa", offpeak: "Nižja tarifa", blocks: "Zadnji dnevni časovni bloki",
      block: "Blok",
      power: "Dogovorjena moč", history: "Spremembe dnevnega odjema v HA",
      historyInfo: "Graf prikazuje datum spremembe senzorja v Home Assistantu, ne datuma meritve.",
      noHistory: "Zgodovina bo na voljo, ko HA shrani spremembe dnevnega senzorja.",
      noData: "Ni podatkov", stale: "Podatki so zastareli", fresh: "Podatki so sveži",
      last: "Zadnja objavljena meritev", refresh: "Osveži podatke", refreshing: "Osvežujem …",
      failed: "Osvežitev ni uspela", noMeter: "Ni najdenih entitet Moj Elektro.",
      multiple: "Nastavljenih je več merilnih mest. V nastavitvah kartice določi meter_id.",
      unknownMeter: "Za izbrani meter_id ni najdenih entitet Moj Elektro.",
      registryError: "Entitet ni bilo mogoče prebrati iz registra Home Assistanta.",
    },
    en: {
      title: "Moj Elektro", subtitle: "Energy overview", daily: "Latest daily import",
      monthly: "Monthly import", total: "Total import", quarter: "Latest 15 minutes",
      output: "Export to grid", net: "Net daily import", tariffs: "Tariffs this month",
      dailyOutput: "Latest daily export", totalOutput: "Total export",
      cost: "Estimated monthly energy cost", costInfo: "Energy only; excludes network charges, levies and taxes.",
      peak: "Peak tariff", offpeak: "Off-peak tariff", blocks: "Latest daily network blocks",
      block: "Block",
      power: "Contracted power", history: "Daily import changes in HA",
      historyInfo: "The chart uses the date the sensor changed in Home Assistant, not the reading date.",
      noHistory: "History appears after HA records changes to the daily sensor.",
      noData: "No data", stale: "Data is stale", fresh: "Data is fresh",
      last: "Last published reading", refresh: "Refresh data", refreshing: "Refreshing …",
      failed: "Refresh failed", noMeter: "No Moj Elektro entities were found.",
      multiple: "More than one meter is configured. Set meter_id in the card configuration.",
      unknownMeter: "No Moj Elektro entities were found for this meter_id.",
      registryError: "Could not read the Home Assistant entity registry.",
    },
  };

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[c]);
  }

  function finiteState(state) {
    if (!state || state.state === "" || state.state === null ||
        state.state === "unknown" || state.state === "unavailable" ||
        (typeof state.state === "string" && !state.state.trim())) return null;
    const value = Number(state.state);
    return Number.isFinite(value) ? value : null;
  }

  function resolveEntities(entries, meterId) {
    const groups = new Map();
    for (const entry of entries) {
      if (entry.platform !== "mojelektro" || entry.disabled_by) continue;
      const match = /^(.*)-(sensor|button|binary_sensor)\.mojelektro_(.+)$/.exec(entry.unique_id || "");
      if (!match || !KEYS.includes(match[3])) continue;
      if (!groups.has(match[1])) groups.set(match[1], {});
      groups.get(match[1])[match[3]] = entry.entity_id;
    }
    if (meterId) return groups.get(meterId) || null;
    if (groups.size !== 1) return null;
    return groups.values().next().value;
  }

  function historyDays(payload, start, end) {
    const days = new Map();
    for (const row of Array.isArray(payload) && Array.isArray(payload[0]) ? payload[0] : []) {
      const time = Date.parse(row.last_changed || row.lc || row.last_updated || "");
      const value = finiteState(row.s !== undefined ? { state: row.s } : row);
      if (!Number.isFinite(time) || time < start || time > end || value === null) continue;
      const day = new Date(time).toLocaleDateString("en-CA");
      if (!days.has(day) || time >= days.get(day).time) days.set(day, { day, value, time });
    }
    return [...days.values()].sort((a, b) => a.time - b.time).slice(-30);
  }

  class MojElektroEnergyCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._entities = null;
      this._history = [];
      this._historyAt = 0;
      this._generation = 0;
      this._message = null;
      this._busy = false;
      this._refreshError = false;
      this._lastRender = null;
    }

    setConfig(config) {
      if (config.meter_id !== undefined && typeof config.meter_id !== "string") {
        throw new Error("meter_id must be a string");
      }
      for (const key of ["price_vt", "price_mt"]) {
        if (config[key] !== undefined &&
            (typeof config[key] !== "number" || !Number.isFinite(config[key]) || config[key] < 0)) {
          throw new Error(`${key} must be a non-negative number in EUR/kWh`);
        }
      }
      this._config = { ...config };
      this._entities = null;
      this._history = [];
      this._historyAt = 0;
      this._loadingHistory = false;
      this._message = null;
      this._lastRender = null;
      this._generation++;
      if (this.isConnected && this._hass) this._loadEntities();
    }

    set hass(hass) {
      this._hass = hass;
      if (!this.isConnected || !this._config) return;
      if (!this._entities && !this._resolving) this._loadEntities();
      if (this._entities && !this._loadingHistory && Date.now() - this._historyAt >= 30 * 60_000) this._loadHistory();
      this._render();
    }

    connectedCallback() {
      if (this._hass && this._config && !this._entities) this._loadEntities();
      this._render();
    }

    disconnectedCallback() {
      this._generation++;
      this._resolving = false;
      this._loadingHistory = false;
    }

    getCardSize() { return 12; }

    _language() {
      return (this._config?.language || this._hass?.language || "sl").startsWith("sl") ? "sl" : "en";
    }

    async _loadEntities() {
      if (this._resolving || !this._hass) return;
      this._resolving = true;
      const generation = ++this._generation;
      try {
        const entries = await this._hass.callWS({ type: "config/entity_registry/list" });
        if (generation !== this._generation || !this.isConnected) return;
        const meterId = this._config?.meter_id;
        this._entities = resolveEntities(entries, meterId) || {};
        const groups = new Set(entries.filter((entry) => entry.platform === "mojelektro")
          .map((entry) => /^(.*)-(?:sensor|button|binary_sensor)\.mojelektro_/.exec(entry.unique_id || "")?.[1])
          .filter(Boolean));
        this._message = Object.keys(this._entities).length ? null :
          meterId ? "unknownMeter" : groups.size > 1 ? "multiple" : "noMeter";
        this._render();
        this._loadHistory();
      } catch (_error) {
        if (generation === this._generation && this.isConnected) {
          this._message = "registryError";
          this._render();
        }
      } finally {
        if (generation === this._generation) this._resolving = false;
      }
    }

    async _loadHistory() {
      const entityId = this._entities?.daily_input;
      if (!entityId || this._loadingHistory || Date.now() - this._historyAt < 30 * 60_000) return;
      this._loadingHistory = true;
      const generation = this._generation;
      const end = Date.now();
      const start = end - 31 * 24 * 60 * 60_000;
      try {
        const query = `filter_entity_id=${encodeURIComponent(entityId)}&end_time=${encodeURIComponent(new Date(end).toISOString())}&minimal_response`;
        const result = await this._hass.callApi("GET", `history/period/${new Date(start).toISOString()}?${query}`);
        if (generation === this._generation && this.isConnected) {
          this._history = historyDays(result, start, end);
          this._render();
        }
      } catch (_error) {
        // Recorder/history can be disabled. The rest of the card stays usable.
      } finally {
        if (generation === this._generation) {
          this._historyAt = Date.now();
          this._loadingHistory = false;
        }
      }
    }

    _value(key) { return finiteState(this._hass?.states[this._entities?.[key]]); }

    _sameSourceTime(first, second) {
      const a = this._hass?.states[this._entities?.[first]]?.attributes?.source_timestamp;
      const b = this._hass?.states[this._entities?.[second]]?.attributes?.source_timestamp;
      return Boolean(a && b && Date.parse(a) === Date.parse(b));
    }

    _number(value, digits = 2) {
      return value === null ? "—" : new Intl.NumberFormat(this._language(), {
        maximumFractionDigits: digits, minimumFractionDigits: digits,
      }).format(value);
    }

    _metric(label, key, unit = "kWh") {
      const value = this._value(key);
      return `<div class="metric"><span>${label}</span><strong>${this._number(value)}</strong><small>${value === null ? "" : unit}</small></div>`;
    }

    _split(title, left, right, first, second) {
      if (left === null && right === null) return "";
      const a = Math.max(0, left || 0);
      const b = Math.max(0, right || 0);
      const percent = a + b ? (a / (a + b)) * 100 : 50;
      return `<section><h3>${title}</h3><div class="split-label"><span>${first}: ${this._number(left)} kWh</span><span>${second}: ${this._number(right)} kWh</span></div><div class="track"><div class="peak" style="width:${percent}%"></div></div></section>`;
    }

    _historyChart(t) {
      if (!this._history.length) return `<p class="empty">${t.noHistory}</p>`;
      const values = this._history;
      const max = Math.max(1, ...values.map((row) => Math.max(0, row.value)));
      const bars = values.map((row) => {
        const height = Math.max(2, Math.min(100, Math.max(0, row.value) / max * 100));
        const date = new Date(row.time).toLocaleDateString(this._language(), { day: "numeric", month: "short" });
        return `<div class="bar" style="height:${height}%" title="${escapeHtml(date)}: ${this._number(row.value)} kWh"><span>${escapeHtml(date)}</span></div>`;
      }).join("");
      return `<div class="chart" role="img" aria-label="${escapeHtml(t.history)}">${bars}</div><p class="hint">${t.historyInfo}</p>`;
    }

    _render() {
      if (!this.shadowRoot || !this._config || !this._hass) return;
      const signature = JSON.stringify([
        this._config.title, this._config.language, this._config.price_vt,
        this._config.price_mt, this._hass.language,
        this._message, this._busy, this._refreshError, this._history,
        this._entities, ...Object.values(this._entities || {}).map((id) => [
          this._hass.states[id]?.state, this._hass.states[id]?.attributes?.source_timestamp,
        ]),
      ]);
      if (signature === this._lastRender) return;
      this._lastRender = signature;
      const t = LABELS[this._language()];
      const title = escapeHtml(this._config.title || t.title);
      if (this._message) {
        this.shadowRoot.innerHTML = `<ha-card><div class="notice">${escapeHtml(t[this._message])}</div></ha-card>`;
        return;
      }
      if (!this._entities) return;
      const blocks = Array.from({ length: 5 }, (_, i) => this._value(`daily_input_blok_${i + 1}`));
      const power = Array.from({ length: 5 }, (_, i) => this._value(`casovni_blok_${i + 1}`));
      const hasBlocks = blocks.some((v) => v !== null);
      const hasPower = power.some((v) => v !== null);
      const output = this._value("daily_output");
      const input = this._value("daily_input");
      const monthlyPeak = this._value("monthly_input_peak");
      const monthlyOffpeak = this._value("monthly_input_offpeak");
      const estimatedCost = this._config.price_vt !== undefined && this._config.price_mt !== undefined &&
        monthlyPeak !== null && monthlyOffpeak !== null &&
        this._sameSourceTime("monthly_input_peak", "monthly_input_offpeak") ?
        monthlyPeak * this._config.price_vt + monthlyOffpeak * this._config.price_mt : null;
      const net = input !== null && output !== null &&
        this._sameSourceTime("daily_input", "daily_output") ? input - output : null;
      const latest = this._hass.states[this._entities.last_published_reading]?.state;
      const latestTime = latest && !["unknown", "unavailable"].includes(latest) && !Number.isNaN(Date.parse(latest))
        ? new Date(latest).toLocaleString(this._language(), { dateStyle: "medium", timeStyle: "short" }) : t.noData;
      const stale = this._hass.states[this._entities.data_stale]?.state;
      const staleBadge = stale === "on" || stale === "off" ?
        `<span class="badge ${stale === "on" ? "warn" : ""}">${stale === "on" ? t.stale : t.fresh}</span>` : "";
      this.shadowRoot.innerHTML = `
        <style>
          :host { display:block; --accent:#20b4bd; --accent2:#285f91; --muted:var(--secondary-text-color,#8b959e); }
          ha-card { display:block; overflow:hidden; color:var(--primary-text-color); background:var(--ha-card-background,var(--card-background-color)); }
          .wrap { padding:22px; background:radial-gradient(circle at 94% 0%,rgba(32,180,189,.18),transparent 35%); }
          header { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:22px; }
          h2 { margin:0 0 4px; font-size:1.65rem; letter-spacing:-.03em; }
          h3 { margin:0 0 14px; font-size:1rem; }
          .sub,.hint,.empty { color:var(--muted); font-size:.82rem; }
          .badge { border-radius:40px; padding:6px 10px; font-size:.73rem; background:rgba(32,180,189,.13); color:var(--primary-text-color); white-space:nowrap; }
          .badge.warn { background:rgba(240,165,35,.22); }
          .metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }
          .metric { border:1px solid var(--divider-color,rgba(120,130,140,.2)); border-radius:14px; padding:15px; min-width:0; }
          .metric span { display:block; min-height:2.4em; font-size:.79rem; color:var(--muted); }
          .metric strong { display:inline-block; margin-top:7px; font-size:clamp(1.1rem,2.6vw,1.7rem); letter-spacing:-.03em; word-break:break-word; }
          .metric small { margin-left:4px; color:var(--muted); }
          .cost { font-size:1.6rem; font-weight:700; color:var(--accent2); }
          .sections { display:grid; grid-template-columns:1fr 1fr; gap:22px; margin-top:22px; }
          section { min-width:0; border-top:1px solid var(--divider-color,rgba(120,130,140,.2)); padding-top:19px; }
          .split-label { display:flex; justify-content:space-between; gap:8px; font-size:.8rem; margin-bottom:10px; }
          .track { width:100%; height:12px; background:var(--accent2); border-radius:20px; overflow:hidden; }
          .peak { height:100%; background:var(--accent); }
          .rows { display:grid; gap:9px; font-size:.86rem; }
          .row { display:grid; grid-template-columns:78px 1fr auto; gap:10px; align-items:center; }
          .rail { height:8px; background:rgba(120,130,140,.13); border-radius:10px; overflow:hidden; }
          .fill { height:100%; border-radius:10px; background:var(--accent); }
          .chart { display:flex; height:105px; gap:3px; align-items:flex-end; padding:8px 0 24px; border-bottom:1px solid var(--divider-color); }
          .bar { background:linear-gradient(var(--accent),var(--accent2)); border-radius:3px 3px 0 0; flex:1; min-width:2px; position:relative; }
          .bar span { display:none; position:absolute; top:100%; left:0; margin-top:5px; white-space:nowrap; font-size:.65rem; color:var(--muted); }
          .bar:first-child span,.bar:last-child span { display:block; }
          .bar:last-child span { left:auto; right:0; }
          .footer { margin-top:20px; display:flex; align-items:center; justify-content:space-between; gap:12px; color:var(--muted); font-size:.78rem; }
          button { border:0; border-radius:20px; color:var(--primary-text-color); background:rgba(32,180,189,.16); padding:8px 12px; cursor:pointer; font:inherit; }
          button:disabled { opacity:.5; cursor:default; }
          .notice { padding:24px; }
          @media(max-width:650px) { .metrics { grid-template-columns:repeat(2,minmax(0,1fr)); } .sections { grid-template-columns:1fr; } .wrap { padding:17px; } }
        </style>
        <ha-card><div class="wrap">
          <header><div><h2>${title}</h2><div class="sub">${t.subtitle}</div></div>${staleBadge}</header>
          <div class="metrics">${this._metric(t.daily, "daily_input")}${this._metric(t.monthly, "monthly_input")}${this._metric(t.total, "total_input")}${this._metric(t.quarter, "15min_input")}</div>
          <div class="sections">
            ${this._split(t.tariffs, monthlyPeak, monthlyOffpeak, t.peak, t.offpeak)}
            ${output !== null ? `<section><h3>${t.output}</h3><div class="metrics" style="grid-template-columns:repeat(2,minmax(0,1fr))">${this._metric(t.dailyOutput,"daily_output")}${this._metric(t.totalOutput,"total_output")}${net !== null ? `<div class="metric"><span>${t.net}</span><strong>${this._number(net)}</strong><small>kWh</small></div>` : ""}</div></section>` : ""}
            ${estimatedCost !== null ? `<section><h3>${t.cost}</h3><div class="cost">${new Intl.NumberFormat(this._language(), { style: "currency", currency: "EUR" }).format(estimatedCost)}</div><p class="hint">${t.costInfo}</p></section>` : ""}
            ${hasBlocks ? `<section><h3>${t.blocks}</h3><div class="rows">${blocks.map((v,i) => `<div class="row"><span>${t.block} ${i + 1}</span><div class="rail"><div class="fill" style="width:${Math.max(0,Math.min(100,(v || 0) / Math.max(1,...blocks.filter((n) => n !== null)) * 100))}%"></div></div><span>${this._number(v)} kWh</span></div>`).join("")}</div></section>` : ""}
            ${hasPower ? `<section><h3>${t.power}</h3><div class="rows">${power.map((v,i) => `<div class="row"><span>${t.block} ${i + 1}</span><div class="rail"><div class="fill" style="width:${Math.max(0,Math.min(100,(v || 0) / Math.max(1,...power.filter((n) => n !== null)) * 100))}%"></div></div><span>${this._number(v)} kW</span></div>`).join("")}</div></section>` : ""}
            <section class="history"><h3>${t.history}</h3>${this._historyChart(t)}</section>
          </div>
          <div class="footer"><span>${t.last}: ${escapeHtml(latestTime)}${this._refreshError ? ` · ${t.failed}` : ""}</span>${this._entities.refresh_data ? `<button type="button" ${this._busy ? "disabled" : ""}>${this._busy ? t.refreshing : t.refresh}</button>` : ""}</div>
        </div></ha-card>`;
      const button = this.shadowRoot.querySelector("button");
      if (button) button.addEventListener("click", () => this._refresh());
    }

    async _refresh() {
      const entityId = this._entities?.refresh_data;
      if (!entityId || this._busy) return;
      this._busy = true;
      this._refreshError = false;
      this._render();
      try {
        await this._hass.callService("button", "press", { entity_id: entityId });
        this._historyAt = 0;
        this._loadHistory();
      } catch (_error) {
        this._refreshError = true;
      } finally {
        this._busy = false;
        this._render();
      }
    }
  }

  if (!customElements.get(CARD)) customElements.define(CARD, MojElektroEnergyCard);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === CARD)) window.customCards.push({
    type: CARD,
    name: "Moj Elektro energy overview",
    description: "Optional dashboard using the Moj Elektro Home Assistant entities.",
    preview: false,
    documentationURL: "https://github.com/jursko90/homeassistant-mojelektro",
  });
})();
