/* Dashboard front end: fetches the Flask API and draws charts with D3 v7. */
(function () {
  "use strict";

  const state = { period: "6m", branch: "all", service: "all", metric: "revenue", grain: "month", techOrder: "bottom" };
  let meta = null;            // /api/filters
  let metrics = null;         // /api/metrics (labels + formats come from the server)
  const cache = {};           // last data per chart, so resize can redraw without refetching

  const $ = (s) => document.querySelector(s);
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const tip = $("#tip");

  /* ------------------------------------------------------------ formats */
  const fmt = {
    currency: (v) => (v == null ? "n/a" : d3.format("$.3~s")(v).replace("G", "B")),
    currency2: (v) => (v == null ? "n/a" : d3.format("$,.2f")(v)),
    number: (v) => (v == null ? "n/a" : d3.format(",.0f")(v)),
    percent: (v) => (v == null ? "n/a" : d3.format(".1%")(v)),
    score: (v) => (v == null ? "n/a" : d3.format(".2f")(v)),
  };
  const fmtMetric = (id, v) => fmt[metrics[id].format](v);
  const parseDate = d3.utcParse("%Y-%m-%d");
  const monthLabel = d3.utcFormat("%b %Y");
  const dayLabel = d3.utcFormat("%b %-d, %Y");

  /* ------------------------------------------------------------ helpers */
  function setStatus(msg, isErr) {
    const el = $("#status");
    el.textContent = msg || "";
    el.classList.toggle("err", !!isErr);
  }

  function periodDates() {
    const [maxY, maxM, maxD] = meta.max_date.split("-").map(Number);
    const pad = (n) => String(n).padStart(2, "0");
    const first = (y, m) => `${y}-${pad(m)}-01`;
    let start;
    if (state.period === "all") start = meta.min_date;
    else if (state.period === "ytd") start = first(maxY, 1);
    else {
      const back = state.period === "12m" ? 11 : 5;
      const idx = maxY * 12 + (maxM - 1) - back;
      start = first(Math.floor(idx / 12), (idx % 12) + 1);
    }
    return { start, end: meta.max_date };
  }

  function query(extra = {}, omit = []) {
    const { start, end } = periodDates();
    const p = new URLSearchParams({ start, end, branch: state.branch, service: state.service, ...extra });
    omit.forEach((k) => p.delete(k));
    return p.toString();
  }

  async function api(path, extra, omit) {
    const res = await fetch(`/api/${path}?${query(extra, omit)}`);
    const body = await res.json();
    if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
    return body;
  }

  function showTip(html, evt) {
    tip.innerHTML = html;
    tip.hidden = false;
    const pad = 12;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let x = evt.clientX + pad, y = evt.clientY + pad;
    if (x + w > window.innerWidth - 8) x = evt.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = evt.clientY - h - pad;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }
  const hideTip = () => { tip.hidden = true; };
  const el = (s) => $(s);
  const widthOf = (sel) => Math.max(280, el(sel).clientWidth);

  /* ---------------------------------------------------------------- KPIs */
  function renderKpis(data) {
    const wrap = $("#kpis");
    wrap.innerHTML = "";
    data.kpis.forEach((k) => {
      const card = document.createElement("div");
      card.className = "kpi";
      let cls = "na", text = "No prior-year data";
      if (k.delta != null) {
        const up = k.delta > 0, flat = Math.abs(k.delta) < 0.05;
        const arrow = flat ? "▬" : up ? "▲" : "▼";
        const goodDir = k.good === "up" ? up : !up;
        cls = flat ? "flat" : goodDir ? "good" : "bad";
        const mag = Math.abs(k.delta).toFixed(k.delta_unit === "pts" ? 2 : 1);
        text = `${arrow} ${up ? "+" : "-"}${mag}${k.delta_unit === "pts" ? " pts" : "%"} vs same dates last year`;
      }
      card.innerHTML = `<div class="name">${k.label}</div>
        <div class="val">${fmt[k.format](k.value)}</div>
        <div class="delta ${cls}">${text}</div>`;
      card.setAttribute("aria-label", `${k.label}: ${fmt[k.format](k.value)}. ${text}`);
      card.appendChild(spark(k.spark));
      wrap.appendChild(card);
    });
    const p = data.prior_period;
    $("#kpi-note").textContent = p.available
      ? `Comparison period: ${p.start} to ${p.end} (same dates one year earlier, so seasons line up).`
      : "There is no data for the same dates last year, so changes are not shown for this period.";
  }

  function spark(points) {
    const w = 180, h = 34;
    const svg = d3.create("svg").attr("viewBox", `0 0 ${w} ${h}`).attr("aria-hidden", "true");
    const pts = points.filter((d) => d.y != null);
    if (pts.length > 1) {
      const x = d3.scaleLinear([0, pts.length - 1], [2, w - 2]);
      const y = d3.scaleLinear(d3.extent(pts, (d) => d.y), [h - 4, 4]);
      svg.append("path").attr("d", d3.line().x((d, i) => x(i)).y((d) => y(d.y))(pts))
        .attr("fill", "none").attr("stroke", css("--accent")).attr("stroke-width", 1.75);
      const last = pts[pts.length - 1];
      svg.append("circle").attr("cx", x(pts.length - 1)).attr("cy", y(last.y)).attr("r", 2.6).attr("fill", css("--accent"));
    }
    return svg.node();
  }

  /* --------------------------------------------------------------- trend */
  function renderTrend(data) {
    cache.trend = data;
    const host = $("#trend");
    host.innerHTML = "";
    const m = data.metric, series = data.series.filter((d) => d.y != null);
    const label = metrics[m].label;
    const W = widthOf("#trend"), H = W < 520 ? 260 : 320;
    const mg = { t: 16, r: 78, b: 30, l: 56 };
    const svg = d3.select(host).append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    $("#trend").setAttribute("aria-label",
      `${label} ${data.grain}ly line chart, ${series.length} points. A table version is below.`);
    if (!series.length) { host.textContent = "No data for these filters."; return; }

    const xs = series.map((d) => parseDate(d.x));
    const x = d3.scaleUtc(d3.extent(xs), [mg.l, W - mg.r]);
    const zeroBase = m === "revenue" || m === "completed_visits";
    let [lo, hi] = d3.extent(series, (d) => d.y);
    if (!zeroBase) { const padv = (hi - lo) * 0.25 || hi * 0.05; lo -= padv; hi += padv; } else lo = 0;
    const y = d3.scaleLinear([lo, hi], [H - mg.b, mg.t]).nice();

    svg.append("g").attr("class", "grid").attr("transform", `translate(${mg.l},0)`)
      .call(d3.axisLeft(y).ticks(5).tickSize(-(W - mg.l - mg.r)).tickFormat(""));
    svg.append("g").attr("class", "axis").attr("transform", `translate(${mg.l},0)`)
      .call(d3.axisLeft(y).ticks(5).tickSize(0).tickPadding(8).tickFormat((v) => fmtMetric(m, v)));
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - mg.b})`)
      .call(d3.axisBottom(x).ticks(W < 520 ? (data.grain === "month" ? d3.utcMonth.every(2) : 3) : 8).tickSizeOuter(0)
        .tickFormat(data.grain === "month" ? d3.utcFormat("%b %y") : d3.utcFormat("%b %-d")));

    const line = d3.line().x((d) => x(parseDate(d.x))).y((d) => y(d.y));
    const area = d3.area().x((d) => x(parseDate(d.x))).y0(y(y.domain()[0])).y1((d) => y(d.y));
    if (zeroBase) svg.append("path").attr("d", area(series)).attr("fill", css("--area"));
    // solid line for complete buckets, dashed for partial first/last bucket
    svg.append("path").attr("d", line(series)).attr("fill", "none")
      .attr("stroke", css("--accent")).attr("stroke-width", 2.5).attr("stroke-linejoin", "round");
    series.filter((d) => d.partial).forEach((d) => {
      svg.append("circle").attr("cx", x(parseDate(d.x))).attr("cy", y(d.y)).attr("r", 4)
        .attr("fill", css("--card")).attr("stroke", css("--accent")).attr("stroke-width", 2);
    });

    // direct label on the latest point (no legend needed for one series)
    const last = series[series.length - 1];
    svg.append("circle").attr("cx", x(parseDate(last.x))).attr("cy", y(last.y)).attr("r", 4.5).attr("fill", css("--accent"));
    svg.append("text").attr("class", "lab").attr("x", x(parseDate(last.x)) + 8).attr("y", y(last.y) + 4)
      .text(fmtMetric(m, last.y));

    // hover / touch
    const focus = svg.append("g").style("display", "none");
    const vline = focus.append("line").attr("y1", mg.t).attr("y2", H - mg.b).attr("stroke", css("--muted")).attr("stroke-dasharray", "3 3");
    const dot = focus.append("circle").attr("r", 5).attr("fill", css("--accent")).attr("stroke", css("--card")).attr("stroke-width", 2);
    const bis = d3.bisector((d) => parseDate(d.x)).center;
    svg.append("rect").attr("x", mg.l).attr("y", mg.t).attr("width", W - mg.l - mg.r).attr("height", H - mg.t - mg.b)
      .attr("fill", "transparent")
      .on("pointermove", (evt) => {
        const [px] = d3.pointer(evt);
        const d = series[bis(series, x.invert(px))];
        focus.style("display", null);
        vline.attr("x1", x(parseDate(d.x))).attr("x2", x(parseDate(d.x)));
        dot.attr("cx", x(parseDate(d.x))).attr("cy", y(d.y));
        showTip(tipHtml(data, d), evt);
      })
      .on("pointerleave", () => { focus.style("display", "none"); hideTip(); });

    // takeaway sentence
    const peak = series.reduce((a, b) => (b.y > a.y ? b : a));
    const per = data.grain === "month" ? monthLabel : dayLabel;
    const chg = last.pop_change == null ? "" : `, ${last.pop_change >= 0 ? "up" : "down"} ${Math.abs(last.pop_change).toFixed(1)}% from the previous ${data.grain}`;
    const partialNote = last.partial ? " (latest bucket is partial)" : "";
    $("#trend-takeaway").textContent =
      `${label} in the latest ${data.grain}${partialNote} was ${fmtMetric(m, last.y)}${chg}. Highest point: ${fmtMetric(m, peak.y)} (${per(parseDate(peak.x))}).`;

    // accessible table
    const tb = $("#trend-table tbody");
    tb.innerHTML = "";
    data.series.forEach((d) => {
      const tr = document.createElement("tr");
      const when = (data.grain === "month" ? monthLabel : dayLabel)(parseDate(d.x)) + (d.partial ? " (partial)" : "");
      tr.innerHTML = `<td>${when}</td><td>${fmtMetric(m, d.y)}</td><td>${d.pop_change == null ? "-" : (d.pop_change >= 0 ? "+" : "") + d.pop_change.toFixed(1) + "%"}</td>`;
      tb.appendChild(tr);
    });
  }

  function tipHtml(data, d) {
    const per = data.grain === "month" ? monthLabel : (v) => "Week of " + dayLabel(v);
    const ch = d.pop_change == null ? "" : `<br>${d.pop_change >= 0 ? "+" : ""}${d.pop_change.toFixed(1)}% vs previous ${data.grain}`;
    return `<strong>${per(parseDate(d.x))}${d.partial ? " (partial)" : ""}</strong><br>${metrics[data.metric].label}: ${fmtMetric(data.metric, d.y)}${ch}`;
  }

  /* ------------------------------------------------------- horizontal bars */
  function renderBars(sel, rows, opts) {
    // opts: label(d), value(d), valueText(d), id(d), selectedId, onPick(id), tooltip(d)
    const host = $(sel);
    host.innerHTML = "";
    const W = widthOf(sel);
    const rowH = 34, mg = { t: 4, r: 96, b: 4, l: Math.min(150, Math.round(W * 0.38)) };
    const H = mg.t + mg.b + rowH * rows.length;
    const svg = d3.select(host).append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    const x = d3.scaleLinear([0, d3.max(rows, opts.value)], [0, W - mg.l - mg.r]);
    const y = d3.scaleBand(rows.map(opts.id), [mg.t, H - mg.b]).paddingInner(0.28);
    const anySelected = opts.selectedId != null && opts.selectedId !== "all";

    rows.forEach((d) => {
      const selected = String(opts.id(d)) === String(opts.selectedId);
      const dim = anySelected && !selected;
      const g = svg.append("g").attr("transform", `translate(0,${y(opts.id(d))})`);
      g.append("text").attr("class", "lab").attr("x", mg.l - 8).attr("y", y.bandwidth() / 2 + 4)
        .attr("text-anchor", "end").text(truncate(opts.label(d), Math.floor(mg.l / 7)));
      g.append("rect").attr("class", "bar").attr("x", mg.l).attr("width", Math.max(2, x(opts.value(d)))).attr("height", y.bandwidth())
        .attr("rx", 3).attr("fill", dim ? css("--bar-dim") : css("--bar"))
        .attr("tabindex", 0).attr("role", "button").attr("aria-pressed", selected)
        .attr("aria-label", `${opts.label(d)}: ${opts.valueText(d)}. ${selected ? "Selected; activate to clear filter." : "Activate to filter."}`)
        .on("pointermove", (evt) => showTip(opts.tooltip(d), evt))
        .on("pointerleave", hideTip)
        .on("focus", function () { const r = this.getBoundingClientRect(); showTip(opts.tooltip(d), { clientX: r.right, clientY: r.top }); })
        .on("blur", hideTip)
        .on("click", () => opts.onPick(selected ? "all" : String(opts.id(d))))
        .on("keydown", (evt) => { if (evt.key === "Enter" || evt.key === " ") { evt.preventDefault(); opts.onPick(selected ? "all" : String(opts.id(d))); } });
      g.append("text").attr("class", "lab").attr("x", mg.l + Math.max(2, x(opts.value(d))) + 6)
        .attr("y", y.bandwidth() / 2 + 4).text(opts.valueText(d));
    });
  }
  const truncate = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

  function renderBranches(data) {
    cache.branches = data;
    renderBars("#branches", data.branches, {
      id: (d) => d.id, label: (d) => d.name, value: (d) => d.revenue,
      valueText: (d) => `${fmt.currency(d.revenue)} · ${d3.format(".0%")(d.revenue_share)}`,
      selectedId: state.branch,
      onPick: (id) => { state.branch = id; $("#branch").value = id; refresh(); },
      tooltip: (d) => `<strong>${d.name}</strong> (${d.region})<br>Revenue ${fmt.currency(d.revenue)} (#${d.revenue_rank})<br>Callback rate ${fmt.percent(d.callback_rate)}<br>Avg CSAT ${fmt.score(d.avg_csat)}`,
    });
  }

  function renderServices(data) {
    cache.services = data;
    renderBars("#services", data.services, {
      id: (d) => d.id, label: (d) => d.name, value: (d) => d.revenue,
      valueText: (d) => `${fmt.currency(d.revenue)} · ${d3.format(".0%")(d.revenue_share)}`,
      selectedId: state.service,
      onPick: (id) => { state.service = id; $("#service").value = id; refresh(); },
      tooltip: (d) => `<strong>${d.name}</strong><br>Revenue ${fmt.currency(d.revenue)}<br>${fmt.number(d.completed_visits)} completed visits`,
    });
  }

  /* -------------------------------------------------------------- heatmap */
  function renderHeat(data) {
    cache.heat = data;
    const host = $("#heat");
    host.innerHTML = "";
    const cells = data.cells;
    if (!cells.length) { host.textContent = "No data for these filters."; return; }
    const rows = Array.from(new Set(cells.map((c) => c.branch))).sort();
    const cols = Array.from(new Set(cells.map((c) => c.service))).sort();
    const avail = widthOf("#heat"), small = avail < 620;
    const W = Math.max(avail, 640);             // scroll sideways on phones instead of squashing the labels
    host.style.overflowX = "auto";
    const mg = { t: 46, r: 8, b: 8, l: 120 };
    const cw = (W - mg.l - mg.r) / cols.length, ch = 30;
    const H = mg.t + mg.b + ch * rows.length;
    const svg = d3.select(host).append("svg").attr("viewBox", `0 0 ${W} ${H}`).style("width", W + "px").style("max-width", "none");
    const vals = cells.map((c) => c.callback_rate).filter((v) => v != null);
    const color = d3.scaleSequential([Math.min(...vals), Math.max(...vals)], (t) => d3.interpolateOranges(0.12 + t * 0.7));
    const x = d3.scaleBand(cols, [mg.l, W - mg.r]).paddingInner(0.06);
    const y = d3.scaleBand(rows, [mg.t, H - mg.b]).paddingInner(0.1);

    cols.forEach((c) => {
      const t = svg.append("text").attr("class", "lab mut").attr("text-anchor", "middle")
        .attr("x", x(c) + x.bandwidth() / 2).attr("y", 14);
      wrapWords(c, 16).forEach((line, i) => t.append("tspan").attr("x", x(c) + x.bandwidth() / 2).attr("dy", i ? 13 : 0).text(line));
    });
    rows.forEach((r) => svg.append("text").attr("class", "lab").attr("x", mg.l - 8).attr("y", y(r) + y.bandwidth() / 2 + 4).attr("text-anchor", "end").text(r));
    const byKey = new Map(cells.map((c) => [c.branch + "|" + c.service, c]));
    rows.forEach((r) => cols.forEach((c) => {
      const d = byKey.get(r + "|" + c);
      const v = d ? d.callback_rate : null;
      const g = svg.append("g");
      const rect = g.append("rect").attr("x", x(c)).attr("y", y(r)).attr("width", x.bandwidth()).attr("height", y.bandwidth()).attr("rx", 3)
        .attr("fill", v == null ? css("--heat-lo") : color(v))
        .attr("tabindex", 0).attr("role", "img")
        .attr("aria-label", `${r}, ${c}: ${v == null ? "not enough visits" : fmt.percent(v) + " callback rate"}`);
      const dark = v != null && d3.lab(color(v)).l < 62;
      g.append("text").attr("x", x(c) + x.bandwidth() / 2).attr("y", y(r) + y.bandwidth() / 2 + 4).attr("text-anchor", "middle")
        .attr("fill", v == null ? css("--muted") : dark ? "#fff" : "#1b2430").attr("font-size", 12)
        .style("pointer-events", "none").text(v == null ? "–" : d3.format(".1%")(v));
      const tipText = () => `<strong>${r}</strong> · ${c}<br>${v == null ? "Fewer than " + data.min_visits + " completed visits" : "Callback rate " + fmt.percent(v) + "<br>" + fmt.number(d.completed_visits) + " completed visits"}`;
      rect.on("pointermove", (evt) => showTip(tipText(), evt)).on("pointerleave", hideTip)
        .on("focus", function () { const b = this.getBoundingClientRect(); showTip(tipText(), { clientX: b.right, clientY: b.top }); }).on("blur", hideTip);
    }));
  }

  function wrapWords(s, n) {
    const out = []; let cur = "";
    s.split(" ").forEach((w) => { if ((cur + " " + w).trim().length > n && cur) { out.push(cur); cur = w; } else cur = (cur + " " + w).trim(); });
    if (cur) out.push(cur);
    return out;
  }

  /* ---------------------------------------------------------- technicians */
  function renderTechs(data) {
    const tb = $("#tech-table tbody");
    tb.innerHTML = "";
    if (!data.technicians.length) { tb.innerHTML = '<tr><td colspan="6">No technicians meet the 50-visit minimum for these filters.</td></tr>'; return; }
    data.technicians.forEach((t) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${t.name}</td><td>${t.branch}</td><td class="num">${fmt.number(t.completed_visits)}</td>
        <td class="num">${fmt.currency(t.revenue)}</td><td class="num">${fmt.percent(t.callback_rate)}</td><td class="num">${fmt.score(t.avg_csat)}</td>`;
      tb.appendChild(tr);
    });
  }

  /* ---------------------------------------------------------------- flow */
  let seq = 0;
  async function refresh() {
    const mine = ++seq;
    syncUrl();
    document.body.classList.add("loading");
    setStatus("Loading…");
    try {
      const [kpis, trend, branches, services, heat, techs] = await Promise.all([
        api("kpis"),
        api("trend", { metric: state.metric, grain: state.grain }),
        api("branches", {}, ["branch"]),          // keep all branches visible so you can switch between them
        api("service-mix", {}, ["service"]),
        api("heatmap"),
        api("technicians", { order: state.techOrder }),
      ]);
      if (mine !== seq) return;                   // a newer request replaced this one
      renderKpis(kpis); renderTrend(trend); renderBranches(branches); renderServices(services); renderHeat(heat); renderTechs(techs);
      const { start, end } = periodDates();
      setStatus(`Showing ${start} to ${end}.`);
    } catch (err) {
      if (mine === seq) setStatus(`Could not load data: ${err.message}`, true);
    } finally {
      if (mine === seq) document.body.classList.remove("loading");
    }
  }

  function syncUrl() {
    const p = new URLSearchParams(state);
    history.replaceState(null, "", "?" + p.toString());
  }

  function press(groupSel, attr, value) {
    document.querySelectorAll(`${groupSel} button`).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset[attr] === value)));
  }

  function buildMetricButtons() {
    const seg = $("#metric-seg");
    seg.innerHTML = "";
    Object.entries(metrics).forEach(([id, m]) => {
      const b = document.createElement("button");
      b.type = "button"; b.dataset.m = id; b.textContent = m.label.replace("Revenue per completed visit", "Rev / visit").replace("Completed visits", "Visits");
      b.setAttribute("aria-pressed", String(id === state.metric));
      b.addEventListener("click", () => { state.metric = id; press("#metric-seg", "m", id); refresh(); });
      seg.appendChild(b);
    });
  }

  async function init() {
    try {
      [meta, metrics] = await Promise.all([fetch("/api/filters").then((r) => r.json()), fetch("/api/metrics").then((r) => r.json())]);
    } catch (e) { setStatus("Could not reach the API. Is the Flask server running?", true); return; }

    const saved = new URLSearchParams(location.search);
    ["period", "branch", "service", "metric", "grain"].forEach((k) => { if (saved.get(k)) state[k] = saved.get(k); });
    if (saved.get("techOrder")) state.techOrder = saved.get("techOrder");
    if (!metrics[state.metric]) state.metric = "revenue";

    const bSel = $("#branch"), sSel = $("#service");
    meta.branches.forEach((b) => bSel.add(new Option(b.name, b.id)));
    meta.services.forEach((s) => sSel.add(new Option(s.name, s.id)));
    bSel.value = state.branch; sSel.value = state.service;
    bSel.addEventListener("change", () => { state.branch = bSel.value; refresh(); });
    sSel.addEventListener("change", () => { state.service = sSel.value; refresh(); });

    document.querySelectorAll("#period-seg button").forEach((b) => b.addEventListener("click", () => { state.period = b.dataset.p; press("#period-seg", "p", state.period); refresh(); }));
    document.querySelectorAll("#grain-seg button").forEach((b) => b.addEventListener("click", () => { state.grain = b.dataset.g; press("#grain-seg", "g", state.grain); refresh(); }));
    document.querySelectorAll("#tech-seg button").forEach((b) => b.addEventListener("click", () => { state.techOrder = b.dataset.o; press("#tech-seg", "o", state.techOrder); refresh(); }));
    $("#reset").addEventListener("click", () => { Object.assign(state, { period: "6m", branch: "all", service: "all", metric: "revenue", grain: "month", techOrder: "bottom" });
      bSel.value = "all"; sSel.value = "all"; press("#period-seg", "p", "6m"); press("#grain-seg", "g", "month"); press("#metric-seg", "m", "revenue"); press("#tech-seg", "o", "bottom"); refresh(); });

    buildMetricButtons();
    press("#period-seg", "p", state.period); press("#grain-seg", "g", state.grain); press("#tech-seg", "o", state.techOrder);

    let t;
    window.addEventListener("resize", () => {
      clearTimeout(t);
      t = setTimeout(() => { if (cache.trend) { renderTrend(cache.trend); renderBranches(cache.branches); renderServices(cache.services); renderHeat(cache.heat); } }, 150);
    });
    refresh();
  }

  init();
})();
