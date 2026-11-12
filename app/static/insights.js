/* Insights page: one API call, four D3 charts, plain-language takeaways. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const tip = $("#tip");
  const pct = d3.format(".1%"), x1 = d3.format(".1f"), money = d3.format("$,.0f"), num = d3.format(",");
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  let data = null;

  function showTip(html, e) {
    tip.innerHTML = html; tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let x = e.clientX + 12, y = e.clientY + 12;
    if (x + w > innerWidth - 8) x = e.clientX - w - 12;
    if (y + h > innerHeight - 8) y = e.clientY - h - 12;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  const hideTip = () => { tip.hidden = true; };
  const fit = (t, px) => { const n = Math.max(6, Math.floor(px / 6.4)); return t.length > n ? t.slice(0, n - 1) + "\u2026" : t; };
  const width = (sel) => Math.max(300, $(sel).clientWidth);

  /* Horizontal bars, sorted, with a reference line. rows: [{label, value, tipHtml, text}] */
  function barsWithRef(sel, rows, ref, aria) {
    const root = d3.select(sel); root.selectAll("*").remove();
    const W = width(sel), rowH = 30, m = { t: 22, r: 70, b: 26, l: Math.min(230, W * 0.5) };
    const H = m.t + m.b + rows.length * rowH;
    const x = d3.scaleLinear([0, d3.max(rows, (d) => d.value) * 1.05], [m.l, W - m.r]);
    const y = d3.scaleBand(rows.map((d) => d.label), [m.t, H - m.b]).padding(0.25);
    const svg = root.append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img").attr("aria-label", aria);
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - m.b})`)
      .call(d3.axisBottom(x).ticks(5).tickFormat((v) => x1(v) + "x"));
    svg.append("g").selectAll("rect").data(rows).join("rect")
      .attr("class", "bar").attr("tabindex", 0)
      .attr("x", m.l).attr("y", (d) => y(d.label)).attr("width", (d) => x(d.value) - m.l).attr("height", y.bandwidth())
      .attr("fill", (d) => (d.value >= 1.5 ? css("--bad") : css("--bar")))
      .attr("aria-label", (d) => d.text)
      .on("mousemove", (e, d) => showTip(d.tipHtml, e)).on("mouseleave", hideTip)
      .on("focus", (e, d) => { const r = e.target.getBoundingClientRect(); showTip(d.tipHtml, { clientX: r.right, clientY: r.top }); })
      .on("blur", hideTip);
    svg.append("g").selectAll("text.l").data(rows).join("text").attr("class", "lab")
      .attr("x", m.l - 8).attr("y", (d) => y(d.label) + y.bandwidth() / 2 + 4).attr("text-anchor", "end")
      .text((d) => fit(d.label, m.l - 12)).append("title").text((d) => d.label);
    svg.append("g").selectAll("text.v").data(rows).join("text").attr("class", "lab mut")
      .attr("x", (d) => x(d.value) + 6).attr("y", (d) => y(d.label) + y.bandwidth() / 2 + 4)
      .text((d) => x1(d.value) + "x");
    svg.append("line").attr("x1", x(ref)).attr("x2", x(ref)).attr("y1", m.t).attr("y2", H - m.b)
      .attr("stroke", css("--ink")).attr("stroke-dasharray", "4 3");
    svg.append("text").attr("class", "lab mut").attr("x", x(ref) + 4).attr("y", 12).text("average");
  }

  function renderHot() {
    const rows = data.hotspots.slice(0, 6).map((d) => ({
      label: `${d.branch}: ${d.service}`, value: d.vs_company,
      text: `${d.branch} ${d.service}: callback rate ${pct(d.callback_rate)}, ${x1(d.vs_company)} times the company rate`,
      tipHtml: `<b>${d.branch}, ${d.service}</b><br>Callback rate ${pct(d.callback_rate)}<br>${num(d.completed_visits)} completed visits`,
    }));
    const top = data.hotspots[0];
    $("#t-hot").textContent = `${top.branch} ${top.service} has a ${pct(top.callback_rate)} callback rate, ${x1(top.vs_company)} times the company rate of ${pct(data.company_callback_rate)}.`;
    $("#a-hot").textContent = "Review treatment procedures and technician training for the top two pairs first; they are specialty services where a repeat visit costs the most.";
    barsWithRef("#c-hot", rows, 1, "Callback rate versus company average for the highest branch and service pairs");
  }

  function renderTech() {
    const rows = data.technicians.slice(0, 6).map((d) => ({
      label: `${d.name} (${d.branch})`, value: d.vs_branch,
      text: `${d.name} in ${d.branch}: callback rate ${pct(d.callback_rate)}, ${x1(d.vs_branch)} times the branch average`,
      tipHtml: `<b>${d.name}, ${d.branch}</b><br>Callback rate ${pct(d.callback_rate)} vs branch ${pct(d.branch_avg)}<br>${num(d.completed_visits)} completed visits`,
    }));
    const t = data.technicians[0];
    $("#t-tech").textContent = `${t.name} in ${t.branch} runs ${x1(t.vs_branch)} times the branch callback rate over ${num(t.completed_visits)} completed visits.`;
    $("#a-tech").textContent = "Pair the top outliers with a high-performing peer for ride-alongs and re-check in a quarter. Use it for coaching, not ranking people.";
    barsWithRef("#c-tech", rows, 1, "Technician callback rate relative to branch average");
  }

  function renderSeason() {
    const root = d3.select("#c-season"); root.selectAll("*").remove();
    const services = [...new Set(data.seasonality.map((d) => d.service))];
    const W = width("#c-season"), m = { t: 22, r: 8, b: 4, l: Math.min(180, W * 0.34) };
    const cw = (W - m.l - m.r) / 12, rh = 28, H = m.t + m.b + services.length * rh;
    const max = d3.max(data.seasonality, (d) => d.index_vs_avg);
    const color = d3.scaleSequential([0, max], (t) => d3.interpolateRgb(css("--heat-lo"), css("--accent"))(t));
    const svg = root.append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img")
      .attr("aria-label", "Heatmap of monthly visit volume by service for 2025");
    MONTHS.forEach((mo, i) => svg.append("text").attr("class", "lab mut").attr("x", m.l + i * cw + cw / 2).attr("y", 14).attr("text-anchor", "middle").text(cw < 30 ? mo[0] : mo));
    services.forEach((s, r) => {
      svg.append("text").attr("class", "lab").attr("x", m.l - 8).attr("y", m.t + r * rh + rh / 2 + 4).attr("text-anchor", "end").text(fit(s, m.l - 12));
      data.seasonality.filter((d) => d.service === s).forEach((d) => {
        svg.append("rect").attr("x", m.l + (d.month - 1) * cw + 1).attr("y", m.t + r * rh + 1)
          .attr("width", cw - 2).attr("height", rh - 2).attr("rx", 3).attr("fill", color(d.index_vs_avg))
          .attr("stroke", d.peak_rank === 1 ? css("--ink") : "none").attr("stroke-width", 2)
          .attr("tabindex", 0).attr("aria-label", `${s}, ${MONTHS[d.month - 1]}: ${x1(d.index_vs_avg)} times average${d.peak_rank === 1 ? ", peak month" : ""}`)
          .on("mousemove", (e) => showTip(`<b>${s}, ${MONTHS[d.month - 1]}</b><br>${num(d.visits)} visits (${x1(d.index_vs_avg)}x average)`, e))
          .on("mouseleave", hideTip);
      });
    });
    const peaks = services.map((s) => data.seasonality.find((d) => d.service === s && d.peak_rank === 1));
    const sorted = [...peaks].sort((a, b) => b.index_vs_avg - a.index_vs_avg);
    $("#t-season").textContent = `${sorted[0].service} is the most seasonal: its ${MONTHS[sorted[0].month - 1]} peak is ${x1(sorted[0].index_vs_avg)} times its monthly average. Outlined cells mark each service's peak.`;
    $("#a-season").textContent = "Plan seasonal hiring and route capacity ahead of each peak, for example mosquito and lawn services before summer and rodent control before winter.";
  }

  function renderPlan() {
    const root = d3.select("#c-plan"); root.selectAll("*").remove();
    const rows = data.plans;
    const W = width("#c-plan"), rowH = 34, m = { t: 6, r: 90, b: 6, l: 110 }, H = m.t + m.b + rows.length * rowH;
    const x = d3.scaleLinear([0, d3.max(rows, (d) => d.revenue_per_visit) * 1.05], [m.l, W - m.r]);
    const y = d3.scaleBand(rows.map((d) => d.plan), [m.t, H - m.b]).padding(0.25);
    const svg = root.append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img").attr("aria-label", "Revenue per visit by customer plan");
    svg.selectAll("rect").data(rows).join("rect").attr("class", "bar").attr("tabindex", 0)
      .attr("x", m.l).attr("y", (d) => y(d.plan)).attr("width", (d) => x(d.revenue_per_visit) - m.l).attr("height", y.bandwidth())
      .attr("fill", css("--bar")).attr("aria-label", (d) => `${d.plan}: ${money(d.revenue_per_visit)} per visit`)
      .on("mousemove", (e, d) => showTip(`<b>${d.plan}</b><br>${money(d.revenue_per_visit)} per visit<br>${num(d.completed_visits)} completed visits`, e)).on("mouseleave", hideTip);
    svg.selectAll("text.l").data(rows).join("text").attr("class", "lab").attr("x", m.l - 8).attr("y", (d) => y(d.plan) + y.bandwidth() / 2 + 4).attr("text-anchor", "end").text((d) => d.plan);
    svg.selectAll("text.v").data(rows).join("text").attr("class", "lab mut").attr("x", (d) => x(d.revenue_per_visit) + 6).attr("y", (d) => y(d.plan) + y.bandwidth() / 2 + 4).text((d) => money(d.revenue_per_visit));
    const hi = rows[0], lo = rows[rows.length - 1];
    $("#t-plan").textContent = `${hi.plan} visits earn ${money(hi.revenue_per_visit)} each versus ${money(lo.revenue_per_visit)} for ${lo.plan}, so the discount for frequent plans is visible per visit.`;
    $("#a-plan").textContent = "Judge plans on lifetime value, not price per visit alone: recurring plans trade a lower price for more visits and steadier revenue.";
  }

  function draw() { if (data) { renderHot(); renderTech(); renderSeason(); renderPlan(); } }

  fetch("/api/insights").then((r) => r.json()).then((d) => {
    data = d; $("#status").textContent = ""; $("#note").textContent = d.note; draw();
  }).catch((e) => { const s = $("#status"); s.textContent = "Could not load insights: " + e.message; s.classList.add("err"); });

  let t; addEventListener("resize", () => { clearTimeout(t); t = setTimeout(draw, 150); });
})();
