"""Compose D3 data-story infographics from stored DataFrames (Wave 4 — scene engine).

Rewritten 2026-05-31 to close the gap between the old 4-template tool
(top_n_bar / time_series_line / composition_donut / kpi_card) and the
target data-stories in ``hackathon/notes/story/infographics/`` (Lorenz/Gini,
regression forest, origin×destination heatmap, GDP-burden scatter, Europe
choropleth, bump-race, dumbbell, multi-panel report stories).

Architecture — a **scene engine**:

    A story is an ordered list of *scenes*. Each scene names a chart
    *archetype* and carries (a) a data slice and (b) narrative text
    (eyebrow / title / lede / caption / annotations / highlight). One scene
    → a single infographic; many scenes → a multi-panel "report" story
    (kicker → hero → stat cards → titled chart panels → methodology),
    exactly like build_concentration/solutions/outcomes.py.

    The bespoke *sticky-scroll* flagship essay is NOT here — that is the
    freehand ``compose_story`` tool's job.

Data injection — the validated ``"__DATA__"`` idiom:

    The HTML scaffold is a raw string carrying ONE quoted token,
    ``"__DATA__"``, inside ``const DATA = "__DATA__";``. The tool computes a
    plain ``data`` dict and does ``scaffold.replace('"__DATA__"', json.dumps(data))``.
    No figure, label, annotation, or hero number is hand-typed in HTML —
    every value is derived from DATA at render time. Single source of truth.

    A scene gets its data two ways:
      • ``variable_name`` + ``mapping`` → the tool shapes the slice from a
        stored DataFrame (sort/topN/group/cumulate), OR
      • inline ``data`` on the scene → the agent passes a precomputed slice
        (used for statistics SQL can't do: Gini value, OLS fit, logistic
        odds-ratios + CIs).
    A comparison bar's ``value`` is ALWAYS the metric being compared (the % or
    figure in the scene's lede) — NEVER the group size / row count. If every
    bar in a group comparison comes out ~equal and ≈ (rows ÷ groups), the
    value column is the group COUNT, not the metric: fix it. Prefer
    ``variable_name`` + ``mapping`` so the tool reads the metric column.

Palette + type — the reconciled RA-editorial token set, mirrored verbatim
from ``skills/design_system/tokens.css`` (oat/ivory canvas, cobalt primary,
amber/cyan/magenta accents; Source Serif 4 / Manrope / JetBrains Mono).

Output (kept compatible with the old return shape so the frontend's
artifact dock keeps working): a standalone single-file HTML uploaded to
``/Volumes/workspace/ai_ops/agent_scratch/infographics/<id>.html`` and a
proxied ``/api/infographics/<id>`` URL.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from io import BytesIO
from typing import Annotated, Any, Callable

import pandas as pd
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore

from tools.compact_ref import _compact_error

logger = logging.getLogger(__name__)


# ── Palette — mirror of skills/design_system/tokens.css (single source) ──
_PALETTE = {
    "paper": "#FAF6EE", "oat": "#F5EFE3", "ink": "#1F1B16", "slate": "#3A3A40",
    "mute": "#9CA0A3", "grey": "#C7C2B6", "hair": "rgba(58,58,64,.12)",
    "signal": "#254BB2", "signal_dim": "#5B79C9", "amber": "#DF9B44",
    "cyan": "#2695AC", "magenta": "#913F82", "alarm": "#A6402E",
    "ink_bg": "#14110D", "on_ink": "#F5EFE3", "on_ink_mute": "#B8B2A6",
    "on_ink_accent": "#DF9B44",
}
# Multi-series visual priority. Highlight-by-colour: most series render `grey`;
# only the entity the sentence names gets an accent, in this order.
_SERIES = ["#254BB2", "#DF9B44", "#2695AC", "#913F82", "#3A3A40", "#9CA0A3"]

_VOLUME_ROOT = "/Volumes/workspace/ai_ops/agent_scratch/infographics"

# Archetypes this engine can render. Keep in sync with the RENDERERS JS map
# and the design_system/infographics SKILL recipes.
_ARCHETYPES = {
    "ranked_bar", "line_multi", "stacked_area", "stacked_area_share",
    "lorenz_gini", "stat", "count_up", "kpi_grid",
    "forest_ci", "heatmap_matrix", "bubble_scatter", "choropleth",
    "dumbbell", "slope", "pyramid", "bar_race", "iceberg", "projection",
    "sankey_corridors",
}

# Legacy template names → archetype (back-compat with the old tool).
_LEGACY_TEMPLATE = {
    "top_n_bar": "ranked_bar",
    "time_series_line": "line_multi",
    "composition_donut": "kpi_grid",   # donut deprecated → KPI grid / ranked_bar preferred
    "kpi_card": "stat",
}


# ── Number formatting (Python side; the JS H.fmt mirrors it) ─────────────
def _fmt_number(v: Any) -> str:
    try:
        n = float(v)
    except Exception:
        return html.escape(str(v))
    a = abs(n)
    if a >= 1e9:
        return f"{n/1e9:.2f}B"
    if a >= 1e6:
        return f"{n/1e6:.2f}M"
    if a >= 1e5:
        return f"{n/1e3:.0f}K"
    if a >= 1e3:
        return f"{n:,.0f}"
    return f"{n:.0f}"


def _infographic_id(title: str, scenes: list) -> str:
    canon = json.dumps([{"t": s.get("type"), "v": s.get("variable_name", ""),
                         "m": s.get("mapping", {})} for s in scenes], sort_keys=True)
    h = hashlib.sha256(f"{title}|{canon}".encode("utf-8")).hexdigest()[:12]
    return f"infographic_{h}"


# ════════════════════════════════════════════════════════════════════════
# HTML SCAFFOLD — raw string, ONE "__DATA__" injection point.
# Body is built by the driver from DATA so no number is hand-typed.
# ════════════════════════════════════════════════════════════════════════
_SCAFFOLD = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>India healthcare data story</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;0,8..60,700;1,8..60,400&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/topojson-client@3/dist/topojson-client.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12.3/dist/d3-sankey.min.js"></script>
<style>
  :root{
    --paper:#FAF6EE;--oat:#F5EFE3;--ink:#1F1B16;--slate:#3A3A40;--mute:#9CA0A3;
    --grey:#C7C2B6;--hair:rgba(58,58,64,.12);
    --signal:#254BB2;--signal-dim:#5B79C9;--amber:#DF9B44;--cyan:#2695AC;
    --magenta:#913F82;--alarm:#A6402E;
    --serif:"Source Serif 4",Georgia,serif;
    --sans:"Manrope",system-ui,-apple-system,"Segoe UI",sans-serif;
    --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.55;-webkit-font-smoothing:antialiased}
  .skip-nav{position:absolute;left:-9999px}.skip-nav:focus{left:16px;top:16px;background:#fff;padding:8px;z-index:9}
  .wrap{max-width:1040px;margin:0 auto;padding:8vh 6vw 6vh}
  .kicker{font-family:var(--mono);font-size:.78rem;letter-spacing:.14em;text-transform:uppercase;color:var(--signal);margin-bottom:1.1rem}
  h1{font-family:var(--serif);font-weight:700;font-size:clamp(2.1rem,4.6vw,3.4rem);line-height:1.06;letter-spacing:-.018em;margin-bottom:1.1rem;max-width:18ch}
  .lede{font-family:var(--serif);font-size:clamp(1.05rem,1.5vw,1.3rem);color:var(--slate);max-width:62ch;margin-bottom:2.4rem}
  .stat-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1.4rem;margin:0 0 3rem}
  .stat-card .n{font-family:var(--serif);font-weight:700;font-size:clamp(2.2rem,5vw,3.4rem);color:var(--signal);line-height:1;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
  .stat-card .l{font-size:.92rem;color:var(--slate);margin-top:.5rem;max-width:34ch}
  .scene{margin:0 0 3.2rem}
  .scene .eyebrow{font-family:var(--mono);font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:var(--mute);margin-bottom:.4rem}
  .scene h2{font-family:var(--serif);font-weight:600;font-size:clamp(1.3rem,2.2vw,1.7rem);line-height:1.15;margin-bottom:.4rem}
  .scene .scene-lede{font-size:1rem;color:var(--slate);max-width:62ch;margin-bottom:1rem}
  .figure{background:#fff;border:1px solid var(--hair);border-radius:10px;padding:20px 18px 12px}
  .figure svg{width:100%;height:auto;display:block;overflow:visible}
  .figure.bare{background:none;border:none;padding:0}
  .caption{font-size:.85rem;color:var(--mute);margin-top:.7rem;max-width:64ch;font-family:var(--sans)}
  .axis text{font-family:var(--mono);font-size:11px;fill:var(--mute)}
  .axis line,.axis path{stroke:var(--hair);shape-rendering:crispEdges}
  .axis-title{font-family:var(--mono);font-size:10px;fill:var(--mute);letter-spacing:.08em;text-transform:uppercase}
  .vlabel{font-family:var(--mono);font-size:11px;fill:var(--ink);font-variant-numeric:tabular-nums}
  .clabel{font-family:var(--sans);font-size:12px;fill:var(--ink);font-weight:600}
  .annot{font-family:var(--serif);font-style:italic;font-size:13px;fill:var(--slate)}
  .big-stat{font-family:var(--serif);font-weight:700;font-size:clamp(3rem,9vw,5.5rem);color:var(--signal);line-height:1;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
  .methodology{margin-top:2.5rem;padding:1.5rem 1.6rem;background:var(--oat);border-left:4px solid var(--signal);border-radius:8px;font-size:.88rem;color:var(--slate)}
  .methodology h3{font-family:var(--mono);font-size:.72rem;text-transform:uppercase;letter-spacing:.1em;color:var(--signal);margin-bottom:.6rem}
  .methodology .src{font-family:var(--mono);font-size:.8rem}
  @keyframes fxIn{from{opacity:0}to{opacity:1}}
  /* Scenes below the fold hold their entrance animation (paused at the `from`
     keyframe) until first scrolled into view; the driver removes .fx-wait ONCE
     and never re-adds it, so the reveal can never re-trigger on scroll. */
  .scene.fx-wait *{animation-play-state:paused!important}
  @media(max-width:820px){.wrap{padding:6vh 6vw}}
  @media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style></head><body>
<a href="#main" class="skip-nav">Skip to content</a>
<div class="wrap" id="main">
  <p class="kicker" id="kicker"></p>
  <h1 id="title"></h1>
  <p class="lede" id="lede"></p>
  <section class="stat-cards" id="stat-cards" hidden></section>
  <main id="scenes"></main>
  <aside class="methodology" id="methodology">
    <h3>How we did this</h3>
    <p id="method-body"></p>
    <p class="src" id="method-src"></p>
  </aside>
</div>
<script>
'use strict';
const DATA = "__DATA__";
const P = {paper:'#FAF6EE',oat:'#F5EFE3',ink:'#1F1B16',slate:'#3A3A40',mute:'#9CA0A3',
  grey:'#C7C2B6',hair:'rgba(58,58,64,.12)',signal:'#254BB2',signalDim:'#5B79C9',
  amber:'#DF9B44',cyan:'#2695AC',magenta:'#913F82',alarm:'#A6402E'};
const SERIES=['#254BB2','#DF9B44','#2695AC','#913F82','#3A3A40','#9CA0A3'];
const RM = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// ── Shared helpers passed to every renderer ──
const H = {
  // business ticks: trailing zeros trimmed (35M, 1.25B — never 35.00M)
  fmt(v){ const a=Math.abs(v);
    const trim=s=>s.replace(/\.0+$/,'').replace(/(\.\d*?)0+$/,'$1');
    if(a>=1e9)return trim((v/1e9).toFixed(2))+'B';
    if(a>=1e6)return trim((v/1e6).toFixed(2))+'M';
    if(a>=1e5)return Math.round(v/1e3)+'K';
    if(a>=1e3)return d3.format(',')(Math.round(v));
    return d3.format('.0f')(v); },
  pct(v,dp){ return (v*100).toFixed(dp==null?1:dp)+'%'; },
  // accent for highlighted entity (string or array), neutral grey otherwise
  hue(name, hl, accent){
    const on = Array.isArray(hl) ? hl.indexOf(name)>=0 : (hl!=null && name===hl);
    return on ? (accent||P.signal) : P.grey; },
  // draw-in: final geometry must already be set; this only fades opacity 0→1.
  // Uses a CSS keyframe animation (NOT a d3 transition) so it is deterministic
  // under headless rasterization AND backgrounded-tab safe — `animation-fill-mode:
  // both` guarantees the element RESTS at opacity 1 even if the tab never animates
  // (a dropped d3 transition would leave it invisible). RM → no motion, full opacity.
  in(sel, dur, delay){ if(RM) return sel;
    sel.style('animation', 'fxIn '+(dur==null?600:dur)+'ms ease '+(delay||0)+'ms both');
    return sel; },
  svg(root, vbW, vbH, label){ return root.append('svg')
    .attr('viewBox',`0 0 ${vbW} ${vbH}`).attr('preserveAspectRatio','xMidYMid meet')
    .attr('role','img').attr('aria-label',label||''); },
  // editorial short names for long official country labels (axis space is scarce)
  shortName(s){ s=String(s==null?'':s);
    const MAP={'United Kingdom of Great Britain and Northern Ireland':'United Kingdom',
      'United States of America':'United States','Iran (Islamic Rep. of)':'Iran',
      'Venezuela (Bolivarian Republic of)':'Venezuela','Syrian Arab Rep.':'Syria',
      'Syrian Arab Republic':'Syria','Dem. Rep. of the Congo':'DR Congo',
      'Democratic Republic of the Congo':'DR Congo','United Rep. of Tanzania':'Tanzania',
      'United Republic of Tanzania':'Tanzania','Russian Federation':'Russia',
      'Netherlands (Kingdom of the)':'Netherlands','Bolivia (Plurinational State of)':'Bolivia',
      'Rep. of Moldova':'Moldova','Republic of Moldova':'Moldova','Rep. of Korea':'South Korea',
      "Dem. People's Rep. of Korea":'North Korea',"Lao People's Dem. Rep.":'Laos',
      'Serbia and Kosovo: S/RES/1244 (1999)':'Serbia & Kosovo','State of Palestine':'Palestine',
      'China, Hong Kong SAR':'Hong Kong','Bosnia and Herzegovina':'Bosnia & Herz.'};
    if(MAP[s]) return MAP[s];
    return s.replace(/\s*\((Kingdom|Islamic Rep\.|Bolivarian Republic|Plurinational State) of(?: the)?\)\s*/,'');
  },
  trunc(s,n){ s=String(s==null?'':s); return s.length>n ? s.slice(0,n-1).replace(/[\s,;:·-]+$/,'')+'…' : s; },
};

// ── RENDERERS map. Contract:
//   RENDERERS[type] = function(root, d, P, H, scene)
//     root  = d3 selection of the scene's empty <div class="figure">
//     d     = the scene's data slice (DATA.scenes[i].data)
//     scene = full scene meta {title,eyebrow,lede,caption,highlight,value_unit,annotations,...}
//   The fn appends its own <svg viewBox=...> and draws. Reduced-motion safe
//   (final geometry first, opacity-only motion via H.in). Highlight-by-colour
//   via H.hue(name, scene.highlight). ──
const RENDERERS = {};

// ranked_bar — horizontal leaderboard, highlight-by-colour.
// data: {rows:[{label,value,highlight?}], value_label?}
RENDERERS.ranked_bar = function(root, d, P, H, scene){
  // Long official labels (e.g. "United Kingdom of Great Britain and Northern
  // Ireland") are shortened editorially + truncated so they never escape the
  // canvas; the full name survives as an SVG <title> tooltip on the tick.
  const rows = (d.rows||[]).map(r=>Object.assign({}, r, {label_s:H.trunc(H.shortName(r.label),24)}));
  const W=640,rh=38,m={top:8,right:74,bottom:34,left:Math.min(190,12+7.4*(d3.max(rows,r=>(r.label_s||'').length)||8))};
  const H_=Math.max(160, m.top+m.bottom+rh*rows.length);
  const svg=H.svg(root,W,H_,scene.title), iw=W-m.left-m.right, ih=H_-m.top-m.bottom;
  const g=svg.append('g').attr('transform',`translate(${m.left},${m.top})`);
  const shortOf={}; rows.forEach(r=>{ shortOf[r.label]=r.label_s; });
  const x=d3.scaleLinear().domain([0,d3.max(rows,r=>r.value)*1.12]).range([0,iw]);
  const y=d3.scaleBand().domain(rows.map(r=>r.label)).range([0,ih]).padding(.22);
  g.append('g').attr('class','axis').attr('transform',`translate(0,${ih})`)
    .call(d3.axisBottom(x).ticks(4).tickFormat(H.fmt));
  g.append('g').attr('class','axis').call(d3.axisLeft(y).tickSize(0).tickFormat(l=>shortOf[l]!=null?shortOf[l]:l))
    .call(s=>s.select('.domain').remove()).selectAll('text').style('font-family','var(--sans)').style('fill',P.ink).style('font-size','12px')
    .each(function(l){ if(shortOf[l]!==String(l)) d3.select(this).append('title').text(l); });
  if(scene.value_label) g.append('text').attr('class','axis-title').attr('x',iw).attr('y',ih+30).attr('text-anchor','end').text(String(scene.value_label).toUpperCase());
  rows.forEach((r,i)=>{
    const col = r.highlight!=null ? (r.highlight?P.signal:P.grey) : (scene.highlight!=null ? H.hue(r.label,scene.highlight) : (i===0?P.signal:P.grey));
    // final geometry first; motion = opacity only (reliable under screenshot / backgrounded tab)
    H.in(g.append('rect').attr('y',y(r.label)).attr('height',y.bandwidth()).attr('x',0).attr('rx',2).attr('fill',col).attr('width',x(r.value)), 500, i*35);
    H.in(g.append('text').attr('class','vlabel').attr('x',x(r.value)+6).attr('y',y(r.label)+y.bandwidth()/2+4).text(r.label_fmt||H.fmt(r.value)), 300, 200+i*35);
  });
};

// line_multi — multi-year line(s); end-of-line labels replace a legend.
// data: {series:[{name,points:[{x,y}]}], y_format?('num'|'pct'), y0?}
RENDERERS.line_multi = function(root, d, P, H, scene){
  // Points are coerced numeric and non-finite values dropped; the y-domain
  // EXTENDS BELOW ZERO when the data does (a yoy series with a negative year
  // must dip inside the plot, not dive out of it); paths are clipped to the
  // plot area so no line can ever escape the canvas.
  const S=(d.series||[]).map(s=>({name:s.name,
      points:(s.points||[]).map(p=>({x:+(p&&p.x),y:+(p&&p.y)}))
        .filter(p=>isFinite(p.x)&&isFinite(p.y)).sort((a,b)=>a.x-b.x)}))
    .filter(s=>s.points.length);
  const W=720,Hh=420,m={top:24,right:150,bottom:42,left:64};
  const svg=H.svg(root,W,Hh,scene.title), iw=W-m.left-m.right, ih=Hh-m.top-m.bottom;
  const g=svg.append('g').attr('transform',`translate(${m.left},${m.top})`);
  const all=S.flatMap(s=>s.points); const isPct=d.y_format==='pct';
  if(!all.length){ g.append('text').attr('class','clabel').attr('x',iw/2).attr('y',ih/2).attr('text-anchor','middle').attr('fill',P.mute).text('No data'); return; }
  const x=d3.scaleLinear().domain(d3.extent(all,p=>p.x)).range([0,iw]);
  // y-domain: lines may ZOOM (bars may not). When the data sits far above
  // zero (min > 25% of max — e.g. recognition rates 30–100%), forcing a zero
  // baseline crushes every series into the top band and the end labels
  // collide; zoom to a nice floor under the min instead and SAY SO on the
  // axis. d.y0 explicitly overrides the baseline; negative data still
  // extends the domain below zero.
  const dMin=d3.min(all,p=>p.y), dMax=d3.max(all,p=>p.y);
  let yMin;
  if(d.y0!=null) yMin=Math.min(+d.y0,dMin);
  else if(dMin<0) yMin=dMin;
  else if(dMin>0.25*dMax){ const span=(dMax-dMin)||Math.abs(dMax)||1; yMin=Math.max(0,dMin-span*0.12); }
  else yMin=0;
  const yMax=dMax+(dMax-yMin)*0.06;
  const y=d3.scaleLinear().domain([yMin,yMax]).range([ih,0]).nice();
  const yFmt=isPct?d3.format('.0%'):H.fmt;
  g.append('g').attr('class','axis').attr('transform',`translate(0,${ih})`).call(d3.axisBottom(x).ticks(7).tickFormat(d3.format('d')));
  g.append('g').attr('class','axis').call(d3.axisLeft(y).ticks(5).tickFormat(yFmt));
  if(y.domain()[0]<0) g.append('line').attr('x1',0).attr('x2',iw).attr('y1',y(0)).attr('y2',y(0))
    .attr('stroke',P.mute).attr('stroke-width',1).attr('shape-rendering','crispEdges');
  if(y.domain()[0]>0) g.append('text').attr('class','axis-title').attr('x',0).attr('y',ih+32)
    .text(('y-axis zoomed — starts at '+yFmt(y.domain()[0])+', not zero').toUpperCase());
  if(scene.value_label) g.append('text').attr('class','axis-title').attr('x',-34).attr('y',-10).text(String(scene.value_label).toUpperCase());
  const clipId='lm-clip-'+Math.random().toString(36).slice(2,8);
  svg.append('defs').append('clipPath').attr('id',clipId).append('rect')
    .attr('x',-3).attr('y',-3).attr('width',iw+6).attr('height',ih+6);
  const gp=g.append('g').attr('clip-path','url(#'+clipId+')');
  const ln=d3.line().x(p=>x(p.x)).y(p=>y(p.y)).curve(d3.curveMonotoneX);
  const colOf=(s,i)=>scene.highlight!=null ? H.hue(s.name,scene.highlight,SERIES[i%SERIES.length]) : SERIES[i%SERIES.length];
  S.forEach((s,i)=>{
    // final path drawn immediately; opacity-only fade-in (reliable under screenshot)
    H.in(gp.append('path').datum(s.points).attr('fill','none').attr('stroke',colOf(s,i)).attr('stroke-width',2.4).attr('d',ln), 800, i*140);
  });
  // End-of-line labels replace a legend. Several series often converge on the
  // same final value (rates saturating near 100%), so labels are DODGED: sort
  // by final y, enforce a min vertical gap, clamp inside the plot, and draw a
  // short leader line when a label had to move. When >8 series, label only
  // the IMPORTANT ones (highlighted + final-value extremes + biggest movers).
  let lab=S.map((s,i)=>({s,i,name:H.trunc(H.shortName(s.name),18),
    first:s.points[0],last:s.points[s.points.length-1]}));
  if(lab.length>8){
    const hs=scene.highlight==null?[]:(Array.isArray(scene.highlight)?scene.highlight:[scene.highlight]);
    const byFinal=[...lab].sort((a,b)=>b.last.y-a.last.y);
    const byMove=[...lab].sort((a,b)=>Math.abs(b.last.y-b.first.y)-Math.abs(a.last.y-a.first.y));
    const keep=new Set([...byFinal.slice(0,2),...byFinal.slice(-2),...byMove.slice(0,2)].map(e=>e.i));
    lab.forEach(e=>{ if(hs.indexOf(e.s.name)>=0) keep.add(e.i); });
    lab=lab.filter(e=>keep.has(e.i));
  }
  lab.forEach(e=>{ e.ly=y(e.last.y); });
  lab.sort((a,b)=>a.ly-b.ly);
  const GAP=15;
  lab.forEach((e,k)=>{ if(k) e.ly=Math.max(e.ly,lab[k-1].ly+GAP); });
  for(let k=lab.length-1;k>=0;k--){ const lim=(k===lab.length-1)?ih:lab[k+1].ly-GAP; if(lab[k].ly>lim) lab[k].ly=lim; }
  lab.forEach((e,k)=>{
    const col=colOf(e.s,e.i), x1=x(e.last.x);
    if(Math.abs(e.ly-y(e.last.y))>3)
      H.in(g.append('line').attr('x1',x1+3).attr('x2',x1+7).attr('y1',y(e.last.y)).attr('y2',e.ly)
        .attr('stroke',col).attr('stroke-width',1).attr('stroke-opacity',.6),300,300);
    const t=g.append('text').attr('class','clabel').attr('x',x1+9).attr('y',e.ly+4).attr('fill',col).text(e.name);
    if(e.name!==String(e.s.name)) t.append('title').text(e.s.name);
    H.in(t,400,300+k*60);
  });
};

// stacked_area — absolute composition over time. data:{keys:[],rows:[{x,<key>:v}]}
RENDERERS.stacked_area = function(root, d, P, H, scene){
  const keys=d.keys||[],rows=d.rows||[]; const W=720,Hh=420,m={top:20,right:120,bottom:42,left:64};
  const svg=H.svg(root,W,Hh,scene.title), iw=W-m.left-m.right, ih=Hh-m.top-m.bottom;
  const g=svg.append('g').attr('transform',`translate(${m.left},${m.top})`);
  const stack=d3.stack().keys(keys)(rows);
  const x=d3.scaleLinear().domain(d3.extent(rows,r=>r.x)).range([0,iw]);
  const y=d3.scaleLinear().domain([0,d3.max(stack[stack.length-1],s=>s[1])*1.05]).range([ih,0]).nice();
  g.append('g').attr('class','axis').attr('transform',`translate(0,${ih})`).call(d3.axisBottom(x).ticks(7).tickFormat(d3.format('d')));
  g.append('g').attr('class','axis').call(d3.axisLeft(y).ticks(5).tickFormat(H.fmt));
  const ar=d3.area().x(p=>x(p.data.x)).y0(p=>y(p[0])).y1(p=>y(p[1])).curve(d3.curveMonotoneX);
  stack.forEach((layer,i)=>{
    const col=SERIES[i%SERIES.length];
    H.in(g.append('path').datum(layer).attr('fill',col).attr('fill-opacity',.85).attr('d',ar),600,i*120);
    const lastTop=layer[layer.length-1];
    g.append('text').attr('class','clabel').attr('x',iw+6).attr('y',y((lastTop[0]+lastTop[1])/2)+4).attr('fill',col).style('font-size','11px').text(keys[i]);
  });
};

// stacked_area_share — normalized to 100% share trajectory. data:{keys:[],rows:[{x,<key>:share0..1}]}
RENDERERS.stacked_area_share = function(root, d, P, H, scene){
  const keys=d.keys||[],rows=d.rows||[]; const W=720,Hh=420,m={top:20,right:130,bottom:42,left:54};
  const svg=H.svg(root,W,Hh,scene.title), iw=W-m.left-m.right, ih=Hh-m.top-m.bottom;
  const g=svg.append('g').attr('transform',`translate(${m.left},${m.top})`);
  const stack=d3.stack().keys(keys).offset(d3.stackOffsetExpand)(rows);
  const x=d3.scaleLinear().domain(d3.extent(rows,r=>r.x)).range([0,iw]);
  const y=d3.scaleLinear().domain([0,1]).range([ih,0]);
  g.append('g').attr('class','axis').attr('transform',`translate(0,${ih})`).call(d3.axisBottom(x).ticks(7).tickFormat(d3.format('d')));
  g.append('g').attr('class','axis').call(d3.axisLeft(y).ticks(5).tickFormat(d3.format('.0%')));
  const ar=d3.area().x(p=>x(p.data.x)).y0(p=>y(p[0])).y1(p=>y(p[1])).curve(d3.curveMonotoneX);
  stack.forEach((layer,i)=>{
    const col = scene.highlight!=null ? H.hue(keys[i],scene.highlight,SERIES[i%SERIES.length]) : SERIES[i%SERIES.length];
    H.in(g.append('path').datum(layer).attr('fill',col).attr('fill-opacity',.88).attr('d',ar),600,i*120);
    const lt=layer[layer.length-1];
    g.append('text').attr('class','clabel').attr('x',iw+6).attr('y',y((lt[0]+lt[1])/2)+4).attr('fill',col).style('font-size','11px').text(keys[i]);
  });
};

// lorenz_gini — inequality curve + Gini. data:{lorenz_x:[],lorenz_y:[],gini}
RENDERERS.lorenz_gini = function(root, d, P, H, scene){
  const W=480,Hh=440,m={top:14,right:18,bottom:46,left:50};
  const svg=H.svg(root,W,Hh,scene.title), iw=W-m.left-m.right, ih=Hh-m.top-m.bottom;
  const g=svg.append('g').attr('transform',`translate(${m.left},${m.top})`);
  const x=d3.scaleLinear().domain([0,1]).range([0,iw]), y=d3.scaleLinear().domain([0,1]).range([ih,0]);
  g.append('g').attr('class','axis').attr('transform',`translate(0,${ih})`).call(d3.axisBottom(x).ticks(5).tickFormat(d3.format('.0%')));
  g.append('g').attr('class','axis').call(d3.axisLeft(y).ticks(5).tickFormat(d3.format('.0%')));
  g.append('line').attr('x1',x(0)).attr('y1',y(0)).attr('x2',x(1)).attr('y2',y(1)).attr('stroke',P.mute).attr('stroke-dasharray','4,4');
  const pts=d.lorenz_x.map((xv,i)=>[xv,d.lorenz_y[i]]);
  const area=d3.area().x(p=>x(p[0])).y0(p=>y(p[0])).y1(p=>y(p[1])).curve(d3.curveMonotoneX);
  const line=d3.line().x(p=>x(p[0])).y(p=>y(p[1])).curve(d3.curveMonotoneX);
  H.in(g.append('path').datum(pts).attr('d',area).attr('fill',P.signal).attr('fill-opacity',.12),700);
  g.append('path').datum(pts).attr('d',line).attr('fill','none').attr('stroke',P.signal).attr('stroke-width',2.5);
  g.append('text').attr('class','annot').attr('x',x(.30)).attr('y',y(.74)).attr('fill',P.mute).text('perfect equality →');
  g.append('text').attr('class','annot').attr('x',x(.60)).attr('y',y(.12)).attr('fill',P.signal).text('Gini = '+d.gini.toFixed(2));
  g.append('text').attr('class','clabel').attr('x',iw).attr('y',ih+36).attr('text-anchor','end').attr('fill',P.slate).style('font-size','11px').text('share of country-pairs →');
};

// stat — a single big number (count-up) + context. data:{value, value_fmt?, context?}
RENDERERS.stat = function(root, d, P, H, scene){
  root.classed('bare',true);
  const wrap=root.append('div').style('padding','12px 0 8px');
  // A stat scene without a finite `value` must NEVER print "NaN": fall back to
  // the scene's headline/text (agents often pass {headline, subhead} for a
  // words-as-the-stat callout), sized down when it's a phrase not a number.
  const target=+d.value;
  let txt = (d.value_fmt!=null && d.value_fmt!=='') ? String(d.value_fmt)
          : (isFinite(target) ? H.fmt(target) : null);
  if(txt==null) txt = String(d.headline || d.text || d.label || scene.title || '');
  const big = wrap.append('div').attr('class','big-stat').text(txt);
  if(txt.length>12 || !/\d/.test(txt))
    big.style('font-size','clamp(1.9rem,5.2vw,3.4rem)').style('line-height','1.08').style('letter-spacing','-.015em');
  // FINAL number rendered immediately and left in place — reliable under screenshot
  // / backgrounded tab. A gentle opacity fade is the only motion (no count-from-0,
  // which would show a wrong partial number if a frame is captured mid-tween).
  H.in(big, 700);
  const ctx = d.context || d.subhead || d.sub || '';
  if(ctx) wrap.append('div').attr('class','caption').style('margin-top','.6rem').style('font-size','1rem').style('color',P.slate).text(ctx);
};

// ▼▼▼ PORTED RENDERERS appended below this line (forest_ci, heatmap_matrix,
//     bubble_scatter, choropleth, dumbbell, slope, pyramid, bar_race,
//     iceberg, projection, kpi_grid, count_up). See build_*.py references. ▼▼▼
// ── forest_ci ──
RENDERERS.forest_ci = function(root, d, P, H, scene){
  const R = (d.rows||[]).filter(r=>r && isFinite(r.or) && isFinite(r.lo) && isFinite(r.hi));
  if(!R.length){ root.append('div').attr('class','caption').text('[forest_ci: no rows]'); return; }
  const n = R.length;
  const longest = d3.max(R, r=>(r.name||'').length) || 8;
  const W=820, m={top:20,right:60,bottom:74,left:Math.min(190, 14+7.4*longest)};
  const rowH=Math.max(26, Math.min(44, 360/n));
  const Hh = m.top + m.bottom + rowH*n;
  const svg = H.svg(root, W, Hh, scene.title);
  const iw = W-m.left-m.right, ih = Hh-m.top-m.bottom;
  const g = svg.append('g').attr('transform',`translate(${m.left},${m.top})`);

  // log x-domain padded around the observed CI envelope
  const lo = d3.min(R, r=>r.lo), hi = d3.max(R, r=>r.hi);
  const x = d3.scaleLog().domain([lo*0.85, hi*1.12]).range([0,iw]);
  const y = d3.scaleBand().domain(R.map(r=>r.iso!=null?r.iso:r.name)).range([0,ih]).padding(.34);
  const maxN = d3.max(R, r=>(r.n||0)) || 1;
  const rad = d3.scaleSqrt().domain([0,maxN]).range([3.5,9]);
  const key = r => (r.iso!=null ? r.iso : r.name);

  // pick log ticks that fall inside the domain (nice round multiples)
  const cand=[0.01,0.02,0.05,0.1,0.2,0.5,1,2,5,10];
  let ticks=cand.filter(t=>t>=x.domain()[0] && t<=x.domain()[1]);
  if(ticks.indexOf(1)<0 && 1>=x.domain()[0] && 1<=x.domain()[1]) ticks.push(1);
  if(ticks.length<2) ticks=x.ticks(5);
  ticks=ticks.sort((a,b)=>a-b);

  // colour: highlighted entity → accent (signal); reference category → ink; rest → grey
  const accent = P.signal;
  const colOf = r => r.ref ? P.ink : H.hue(r.name, scene.highlight, accent);

  // gridlines + bottom axis (dashed gridlines, no domain line)
  g.append('g').attr('class','axis').attr('transform',`translate(0,${ih})`)
    .call(d3.axisBottom(x).tickValues(ticks).tickFormat(t=>d3.format('~g')(t)+'×').tickSize(-ih))
    .call(s=>s.selectAll('.tick line').attr('stroke',P.hair).attr('stroke-dasharray','2,3'))
    .call(s=>s.select('.domain').remove());

  // reference line at OR = 1 (the reference category baseline)
  const refName = d.ref || (R.find(r=>r.ref)||{}).name || 'reference';
  g.append('line').attr('x1',x(1)).attr('x2',x(1)).attr('y1',-6).attr('y2',ih)
    .attr('stroke',P.ink).attr('stroke-width',1.2).attr('stroke-dasharray','5,4');
  g.append('text').attr('class','annot').attr('x',x(1)).attr('y',-8)
    .attr('text-anchor','middle').attr('fill',P.ink).text(refName+' = 1');

  // rows — FINAL geometry drawn immediately; H.in fades opacity only
  R.forEach((r,i)=>{
    const cy = y(key(r)) + y.bandwidth()/2;
    const col = colOf(r);
    const grp = g.append('g');
    // row label (right-aligned in the left gutter)
    grp.append('text').attr('class','clabel').attr('x',-10).attr('y',cy+4)
      .attr('text-anchor','end').attr('font-weight', r.ref?700:400)
      .style('font-size','12px').style('fill', r.ref?P.ink:P.slate).text(r.name);
    // 95% CI whisker — partial transparency via stroke-opacity ATTR (not style)
    grp.append('line').attr('x1',x(r.lo)).attr('x2',x(r.hi)).attr('y1',cy).attr('y2',cy)
      .attr('stroke',col).attr('stroke-width',2).attr('stroke-opacity',.55);
    // point estimate dot, sized by caseload
    grp.append('circle').attr('cx',x(r.or)).attr('cy',cy).attr('r',rad(r.n||0))
      .attr('fill',col).attr('stroke',P.paper).attr('stroke-width',1);
    // numeric OR value label (mono) at the high end of the whisker
    grp.append('text').attr('class','vlabel').attr('x',x(r.hi)+7).attr('y',cy+3.5)
      .style('font-size','10.5px').style('fill',P.slate).text(r.or.toFixed(2));
    H.in(grp, 420, i*40);
  });

  // finding annotation on the highlighted (most extreme) row
  const hl = scene.highlight;
  const hlRow = hl!=null ? R.find(r=>r.name===hl || r.iso===hl) : null;
  if(hlRow){
    const cy = y(key(hlRow)) + y.bandwidth()/2;
    const fold = (hlRow.or>0 && hlRow.or<1) ? Math.round(1/hlRow.or)
               : (hlRow.or>=1 ? Math.round(hlRow.or) : null);
    const txt = d.highlight_note ? d.highlight_note
              : (fold!=null ? '← '+fold+'× '+(hlRow.or<1?'lower':'higher')+' than '+refName : '');
    if(txt){
      const right = hlRow.or>=1;
      g.append('text').attr('class','annot').attr('fill',accent)
        .attr('x', right ? x(hlRow.lo)-10 : x(hlRow.or)+rad(hlRow.n||0)+10)
        .attr('y', cy-9).attr('text-anchor', right?'end':'start').text(txt);
    }
  }

  // legend (row 1) + axis title (row 2, centred) — stacked to avoid overlap
  const legItems = [];
  if(scene.highlight!=null) legItems.push([Array.isArray(scene.highlight)?'highlighted':String(scene.highlight), accent]);
  if(R.some(r=>r.ref)) legItems.push([refName+' (reference)', P.ink]);
  legItems.push(['other destinations', P.grey]);
  const lg = g.append('g').attr('transform',`translate(0,${ih+34})`);
  let lx=0;
  legItems.forEach(e=>{
    lg.append('circle').attr('cx',lx+5).attr('cy',-2).attr('r',5).attr('fill',e[1]);
    lg.append('text').attr('class','clabel').attr('x',lx+15).attr('y',2)
      .style('font-size','11px').style('font-weight',400).style('fill',P.slate).text(e[0]);
    lx += 30 + (e[0].length*6.6);
  });
  g.append('text').attr('class','axis-title').attr('x',iw/2).attr('y',ih+60)
    .attr('text-anchor','middle')
    .text(String(scene.value_label || 'odds ratio vs reference — log scale').toUpperCase());
};

// ── heatmap_matrix ──
RENDERERS.heatmap_matrix = function(root, d, P, H, scene){
  let origins = d.origins||[], dests = d.dests||[], cells = d.cells||[];
  // Long-format alias: {rows:[{<rowDim>,<colDim>,<value>}]} → derive the matrix.
  // (Agents sometimes hand the raw frame instead of origins/dests/cells; the
  // old behaviour silently drew ONLY the legend on an empty panel.)
  if((!origins.length || !dests.length || !cells.length) && Array.isArray(d.rows) && d.rows.length){
    const numOf=v=>{const n=parseFloat(v);return isFinite(n)?n:NaN;};
    const keys=Object.keys(d.rows[0]||{});
    const valKey=keys.filter(k=>d.rows.every(r=>isFinite(numOf(r[k]))))
      .sort((a,b)=>(/year|yr|date/i.test(a)?1:0)-(/year|yr|date/i.test(b)?1:0))[0];
    const catKeys=keys.filter(k=>k!==valKey).slice(0,2);
    if(valKey && catKeys.length===2){
      const uniq=k=>[...new Set(d.rows.map(r=>String(r[k])))];
      let rk=catKeys[0], ck=catKeys[1], ru=uniq(rk), cu=uniq(ck);
      if(cu.length>ru.length){ const t=rk; rk=ck; ck=t; const tu=ru; ru=cu; cu=tu; }
      origins=ru.map(v=>({iso:v,name:v}));
      dests=cu.map(v=>({iso:v,name:v}));
      const vmax=d3.max(d.rows,r=>numOf(r[valKey]))||1;
      const isRate=vmax<=1.0001;
      cells=d.rows.map(r=>({o:String(r[rk]), d:String(r[ck]),
        trr:isRate?numOf(r[valKey]):numOf(r[valKey])/vmax,
        raw:numOf(r[valKey]), scaled:!isRate}));
    }
  }
  if(!origins.length || !dests.length || !cells.length){
    root.append('div').attr('class','caption')
      .text('[heatmap_matrix: needs {origins, dests, cells} or long-format {rows}] — no drawable data');
    return;
  }
  const anyScaled = cells.some(c=>c.scaled);
  const oname={}, dname={};
  origins.forEach(o=>{ oname[o.iso]=o.name; });
  dests.forEach(c=>{ dname[c.iso]=c.name; });
  const O = origins.map(o=>o.iso), Dd = dests.map(c=>c.iso);
  const cellMin = (d.cell_min!=null)?d.cell_min:300;

  // Editorially shorten + truncate axis labels (full name survives as an SVG
  // <title> tooltip) so long official country names can't escape the canvas
  // or collide with neighbouring headers.
  const dlabel={}, olabel={};
  Dd.forEach(k=>{ dlabel[k]=H.trunc(H.shortName(dname[k]||k),14); });
  O.forEach(k=>{ olabel[k]=H.trunc(H.shortName(oname[k]||k),16); });

  // layout — wide matrix; right gutter for the spread annotation. The TOP
  // margin is computed from the longest angled header's rotated extent
  // (sin 42° × estimated label width) so headers always clear the canvas —
  // a fixed margin overflows as soon as labels get long.
  const maxDL=d3.max(Dd,k=>dlabel[k].length)||6;
  const mTop=Math.max(70,Math.min(150,Math.round(26+0.67*(8+maxDL*6.2))));
  const W=1040, Hh=700, m={top:mTop,right:152,bottom:48,left:118};
  const iw=W-m.left-m.right, ih=Hh-m.top-m.bottom;
  const svg=H.svg(root,W,Hh,scene.title||'Recognition-rate matrix by nationality and destination');
  const g=svg.append('g').attr('transform',`translate(${m.left},${m.top})`);

  const x=d3.scaleBand().domain(Dd).range([0,iw]).padding(.06);
  const y=d3.scaleBand().domain(O).range([0,ih]).padding(.06);
  // sequential cobalt scale: pale oat (low / strict) → signal (high / generous)
  const color=d3.scaleLinear().domain([0,0.5,1]).range([P.oat,P.signalDim,P.signal]).clamp(true);

  const lookup={};
  cells.forEach(c=>{ lookup[c.o+'|'+c.d]=c; });

  // hatch pattern for suppressed cells (n < cell_min)
  const defs=svg.append('defs');
  const hatch=defs.append('pattern').attr('id','hm-hatch')
    .attr('width',6).attr('height',6).attr('patternUnits','userSpaceOnUse')
    .attr('patternTransform','rotate(45)');
  hatch.append('rect').attr('width',6).attr('height',6).attr('fill',P.paper);
  hatch.append('line').attr('x1',0).attr('y1',0).attr('x2',0).attr('y2',6)
    .attr('stroke',P.grey).attr('stroke-width',1.4);

  // column headers (destination), angled — final position, opacity fade-in
  Dd.forEach(dk=>{
    const cx=x(dk)+x.bandwidth()/2;
    const t=g.append('text').attr('class','clabel')
      .attr('transform',`translate(${cx},-10) rotate(-42)`)
      .attr('text-anchor','start').style('font-size','11px').style('font-weight','400')
      .style('fill',P.slate).text(dlabel[dk]);
    if(dlabel[dk]!==String(dname[dk]||dk)) t.append('title').text(dname[dk]||dk);
    H.in(t, 300, 30);
  });
  // row labels (origin)
  O.forEach(o=>{
    const t=g.append('text').attr('class','clabel').attr('x',-10)
      .attr('y',y(o)+y.bandwidth()/2+4).attr('text-anchor','end')
      .style('font-size','12px').style('font-weight','600').style('fill',P.ink)
      .text(olabel[o]);
    if(olabel[o]!==String(oname[o]||o)) t.append('title').text(oname[o]||o);
    H.in(t, 300, 30);
  });

  // cells — final geometry drawn immediately; entrance = opacity-only via H.in
  let k=0;
  O.forEach((o,ri)=>Dd.forEach(dk=>{
    const c=lookup[o+'|'+dk];
    const cell=g.append('g');
    cell.append('rect').attr('x',x(dk)).attr('y',y(o))
      .attr('width',x.bandwidth()).attr('height',y.bandwidth()).attr('rx',2)
      .attr('fill', c?color(c.trr):'url(#hm-hatch)')
      .attr('stroke',P.paper).attr('stroke-width',1);
    if(c){
      // dark cell (deep cobalt) → light text; pale cell → ink text
      const dark = c.trr>0.45;
      cell.append('text').attr('class','vlabel')
        .attr('x',x(dk)+x.bandwidth()/2).attr('y',y(o)+y.bandwidth()/2+3.5)
        .attr('text-anchor','middle').style('font-size','9.5px')
        .style('fill', dark?P.paper:P.ink)
        .text(c.scaled ? H.fmt(c.raw) : Math.round(c.trr*100)+'%');
    }
    H.in(cell, 380, 80+ (ri*22) + (k%4)*18); k++;
  }));

  // highlight the widest-spread origin row (scene.highlight name, else d.spread.name)
  const hlName = (scene.highlight!=null)
    ? (Array.isArray(scene.highlight)?scene.highlight[0]:scene.highlight)
    : (d.spread && d.spread.name);
  const hlIso = hlName ? (origins.find(o=>o.name===hlName)||{}).iso : null;
  if(hlIso){
    g.append('rect').attr('x',-2).attr('y',y(hlIso)-2)
      .attr('width',iw+4).attr('height',y.bandwidth()+4)
      .attr('fill','none').attr('stroke',P.ink).attr('stroke-width',1.6).attr('rx',3);
    if(d.spread && d.spread.pts!=null){
      H.in(g.append('text').attr('class','annot')
        .attr('x',iw+10).attr('y',y(hlIso)+y.bandwidth()/2+4)
        .attr('text-anchor','start').style('fill',P.signal)
        .text(d.spread.pts+'-pt swing →'), 400, 700);
    }
  }

  // colour legend (sequential gradient bar) — bottom-left
  const lg=g.append('g').attr('transform',`translate(0,${ih+26})`);
  const grad=defs.append('linearGradient').attr('id','hm-grad');
  d3.range(0,1.01,0.1).forEach(t=>grad.append('stop')
    .attr('offset',(t*100)+'%').attr('stop-color',color(t)));
  lg.append('rect').attr('width',200).attr('height',10).attr('rx',2).attr('fill','url(#hm-grad)');
  const vMaxRaw = anyScaled ? (d3.max(cells,c=>c.raw)||1) : 1;
  const tickTxt = anyScaled
    ? [[H.fmt(0),0],[H.fmt(vMaxRaw/2),100],[H.fmt(vMaxRaw),200]]
    : [['0%',0],['50%',100],['100%',200]];
  tickTxt.forEach(p=>
    lg.append('text').attr('class','axis').attr('x',p[1]).attr('y',24)
      .attr('text-anchor','middle').style('font-family','var(--mono)')
      .style('font-size','10px').style('fill',P.mute).text(p[0]));
  lg.append('text').attr('class','axis-title').attr('x',0).attr('y',-6)
    .text(scene.value_label ? ('low ◀ '+String(scene.value_label)+' ▶ high').toUpperCase()
                            : (anyScaled ? 'LOW ◀ VALUE ▶ HIGH' : 'strict ◀ recognition rate ▶ generous'));

  // suppressed-cell note — only when cells are actually missing/hatched
  if(cells.length < O.length*Dd.length){
    lg.append('text').attr('class','annot').attr('x',iw).attr('y',-6)
      .attr('text-anchor','end').style('fill',P.mute).style('font-size','11px')
      .text(anyScaled ? 'hatched = no data' : 'hatched = fewer than '+H.fmt(cellMin)+' decisions');
  }
};

// ── bubble_scatter ──
RENDERERS.bubble_scatter = function(root, d, P, H, scene){
  // Accept `points` OR `rows`, with generous field aliases + string→number
  // coercion (Genie returns numerics as strings) so "No data" only ever means
  // genuinely no usable rows — not a field-name mismatch.
  const numOf=v=>{const n=parseFloat(v);return isFinite(n)?n:NaN;};
  const pickF=(o,keys)=>{for(const k of keys){if(o&&o[k]!=null&&o[k]!=='')return o[k];}return null;};
  const raw=(d.points&&d.points.length?d.points:(d.rows||[]));
  const pts = raw.map(o=>({
      name: H.shortName(String(pickF(o,['name','host','country','label','entity','iso'])||'')),
      name_full: String(pickF(o,['name','host','country','label','entity','iso'])||''),
      gdp: numOf(pickF(o,['gdp','gdp_per_capita','gdp_per_capita_usd','gdp_pc','x'])),
      per1000: numOf(pickF(o,['per1000','refugees_per_1000_residents','per_1000','refugees_per_1000','burden_per_1000','y'])),
      hosted: numOf(pickF(o,['hosted','hosted_refugees','refugees','refugees_hosted','total_hosted','size','n'])),
      region: String(pickF(o,['region','group'])||'Other'),
      note: o&&o.note,
    })).filter(p=>p.gdp>0 && p.per1000>0 && p.hosted>0);
  const W=880, Hh=560, m={top:14,right:154,bottom:54,left:62};
  const svg=H.svg(root,W,Hh,scene.title||'Bubble comparison');
  const iw=W-m.left-m.right, ih=Hh-m.top-m.bottom;
  const g=svg.append('g').attr('transform',`translate(${m.left},${m.top})`);
  if(!pts.length){ g.append('text').attr('class','clabel').attr('x',iw/2).attr('y',ih/2).attr('text-anchor','middle').attr('fill',P.mute).text('No data'); return; }

  // log-log scales (both axes), padded like the reference
  const x=d3.scaleLog().domain([d3.min(pts,p=>p.gdp)*0.8, d3.max(pts,p=>p.gdp)*1.25]).range([0,iw]);
  const y=d3.scaleLog().domain([d3.min(pts,p=>p.per1000)*0.8, d3.max(pts,p=>p.per1000)*1.25]).range([ih,0]);
  // bubble area ∝ hosted (sqrt radius)
  const rad=d3.scaleSqrt().domain([0, d3.max(pts,p=>p.hosted)]).range([3,26]);

  // region → colour (colour ENCODES region here, per the reference). SERIES palette.
  const regions = d.regions || Array.from(new Set(pts.map(p=>p.region)));
  const rc=d3.scaleOrdinal().domain(regions).range(SERIES);

  // gridded log axes (dashed gridlines, no domain line) — matches reference
  const xTicks=[500,1000,2000,5000,10000,20000,50000,100000].filter(v=>v>=x.domain()[0]&&v<=x.domain()[1]);
  const yTicks=[1,2,5,10,20,50,100,200].filter(v=>v>=y.domain()[0]&&v<=y.domain()[1]);
  g.append('g').attr('class','axis').attr('transform',`translate(0,${ih})`)
    .call(d3.axisBottom(x).tickValues(xTicks.length?xTicks:null).tickFormat(v=>'$'+d3.format('~s')(v)).tickSize(-ih))
    .call(s=>s.selectAll('.tick line').attr('stroke',P.hair).attr('stroke-dasharray','2,3'))
    .call(s=>s.select('.domain').remove());
  g.append('g').attr('class','axis')
    .call(d3.axisLeft(y).tickValues(yTicks.length?yTicks:null).tickFormat(d3.format('~r')).tickSize(-iw))
    .call(s=>s.selectAll('.tick line').attr('stroke',P.hair).attr('stroke-dasharray','2,3'))
    .call(s=>s.select('.domain').remove());

  // OLS fit line (log-log): log10(y) = intercept + slope*log10(x). Final geometry now; opacity fade only.
  if(d.intercept!=null && d.slope!=null){
    const gx=[d3.min(pts,p=>p.gdp), d3.max(pts,p=>p.gdp)];
    const ln=gx.map(v=>({gx:v, gy:Math.pow(10, d.intercept + d.slope*Math.log10(v))}));
    H.in(g.append('line').attr('x1',x(ln[0].gx)).attr('y1',y(ln[0].gy))
      .attr('x2',x(ln[1].gx)).attr('y2',y(ln[1].gy))
      .attr('stroke',P.ink).attr('stroke-width',1.6).attr('stroke-dasharray','6,4'), 600);
  }

  // bubbles — FINAL position/radius immediately; partial transparency via fill-opacity ATTR; only opacity fades via H.in
  pts.forEach((p,i)=>{
    H.in(g.append('circle').attr('cx',x(p.gdp)).attr('cy',y(p.per1000)).attr('r',rad(p.hosted))
      .attr('fill',rc(p.region)).attr('fill-opacity',.72)
      .attr('stroke',P.paper).attr('stroke-width',.8), 500, Math.min(i*18,700));
  });

  // labelled notable points on top (reference: any point carrying `note`, or scene.highlight names)
  const hl=scene.highlight;
  const named=p=>{ if(p.note) return true; if(hl==null) return false;
    const hs=Array.isArray(hl)?hl:[hl];
    return hs.indexOf(p.name)>=0 || hs.indexOf(p.name_full)>=0; };
  pts.filter(named).forEach(p=>{
    const r=rad(p.hosted);
    H.in(g.append('text').attr('class','clabel').style('font-size','11px')
      .attr('x',x(p.gdp)+r+3).attr('y',y(p.per1000)-r-2).text(p.name), 400, 300);
  });

  // axis titles (use existing axis-title class)
  g.append('text').attr('class','axis-title').attr('x',iw/2).attr('y',ih+42).attr('text-anchor','middle')
    .text((d.x_label||'GDP per capita, US$ (log scale)')+' →');
  g.append('text').attr('class','axis-title').attr('transform','rotate(-90)')
    .attr('x',-ih/2).attr('y',-44).attr('text-anchor','middle')
    .text('← '+(d.y_label||'y value (log)'));

  // r / R² finding as an italic-serif inline annotation (reference voices this as a finding)
  if(d.r!=null || d.r2!=null){
    const bits=[];
    if(d.r!=null) bits.push('r = '+(d.r>=0?'+':'')+(+d.r).toFixed(2));
    if(d.r2!=null) bits.push('R² = '+H.pct(+d.r2,0));
    if(d.p!=null) bits.push('p = '+(+d.p<0.001?'<0.001':(+d.p).toFixed(3)));
    H.in(g.append('text').attr('class','annot').attr('x',8).attr('y',14)
      .text(bits.join('  ·  ')+' — significant, but practically negligible'), 500, 400);
  }

  // region legend (right gutter) — use clabel class at small size
  const lg=svg.append('g').attr('transform',`translate(${W-142},${m.top+10})`);
  lg.append('text').attr('class','clabel').style('font-size','11px').attr('x',0).attr('y',-4).text('Region');
  regions.forEach((rg,i)=>{
    lg.append('circle').attr('cx',6).attr('cy',12+i*19).attr('r',6).attr('fill',rc(rg)).attr('fill-opacity',.8);
    lg.append('text').attr('class','clabel').style('font-size','11px').style('font-weight','400').attr('fill',P.slate)
      .attr('x',18).attr('y',16+i*19).text(rg);
  });
  // size legend (nested circles) — keyed to hosted-count extent
  const big=d3.max(pts,p=>p.hosted);
  const keys=[big, big/4].filter(v=>v>0);
  const sl=lg.append('g').attr('transform',`translate(0,${14+regions.length*19+10})`);
  sl.append('text').attr('class','clabel').style('font-size','11px').attr('x',0).attr('y',0).text('Bubble = hosted');
  keys.forEach((v,i)=>{
    const cy=24+i*28, rOuter=rad(big);
    sl.append('circle').attr('cx',rOuter).attr('cy',cy).attr('r',rad(v)).attr('fill','none').attr('stroke',P.mute);
    sl.append('text').attr('class','vlabel').style('font-size','10px').attr('x',rOuter*2+8).attr('y',cy+4).text(H.fmt(v));
  });
};

// ── choropleth ──
RENDERERS.choropleth = function(root, d, P, H, scene){
  // Europe-framed choropleth of a 0..1 rate by numeric ISO code.
  // Sequential cobalt scale + legend; grey = no data / not assessed.
  // Needs topojson-client + a world-atlas TopoJSON atlas (see extra_cdn; d3 is
  // already loaded by the scaffold). Faithful port of build_map.py.
  const W=720, Hh=520, mapW=720, mapH=470;
  const svg=H.svg(root, W, Hh, scene.title).style('overflow','hidden');  // clip non-European world features to the frame
  const vals = d.vals || {};                      // {numericISO: {name, rate, n?}}
  const labelSet = new Set((d.label_iso||[]).map(Number));   // ISO codes to direct-label
  const hl = scene.highlight;                     // string name OR array of names to accent
  const nodata = '#E9E4D8';                       // neutral oat for unassessed countries
  const uid = 'choro-'+Math.random().toString(36).slice(2,8);
  // Frame Europe (+ margin) via corner MultiPoint — avoids polygon-winding /
  // overseas-territory bbox inflation. Same trick as the reference build_map.py.
  const corners = {type:'MultiPoint', coordinates: d.frame || [[-12,34],[46,34],[46,72],[-12,72]]};
  // Sequential cobalt ramp: pale -> signal-dim -> signal.
  const color = d3.scaleLinear().domain([0,0.5,1])
    .range(['#E3E9F6', P.signalDim, P.signal]).clamp(true);
  const isOn = name => Array.isArray(hl) ? hl.indexOf(name)>=0 : (hl!=null && name===hl);

  if(typeof topojson === 'undefined'){
    svg.append('text').attr('x',24).attr('y',40).attr('class','annot').attr('fill',P.alarm)
      .text('Map base requires the topojson-client + world-atlas CDN scripts.');
    return;
  }
  const atlasUrl = d.atlas_url || 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json';

  const draw = world => {
    const objects = world.objects.countries || world.objects[Object.keys(world.objects)[0]];
    const countries = topojson.feature(world, objects).features;
    const path = d3.geoPath();
    path.projection(d3.geoMercator().fitExtent([[10,10],[mapW-10,mapH-10]], corners));
    const val = id => vals[+id] || null;

    // FINAL geometry first; opacity-only fade via H.in (screenshot-safe).
    const g = svg.append('g');
    const cs = g.selectAll('path.country').data(countries).join('path')
      .attr('class','country').attr('d', path)
      .attr('fill', dd=>{ const v=val(dd.id); return v ? color(v.rate) : nodata; })
      .attr('stroke', P.paper).attr('stroke-width', 0.6);
    cs.filter(dd=>{ const v=val(dd.id); return v && isOn(v.name); })
      .attr('stroke', P.ink).attr('stroke-width', 1.4).raise();
    cs.append('title').text(dd=>{ const v=val(dd.id);
      return v ? v.name+': '+H.pct(v.rate,0)+' recognised'+(v.n!=null?' (n='+H.fmt(v.n)+')':'') : ''; });
    H.in(g, 700);

    // Direct labels with paper halo. 'clabel' for the accented entity, 'vlabel' otherwise.
    const lg = svg.append('g');
    countries.forEach(dd=>{
      const v=val(dd.id); if(!v || (labelSet.size && !labelSet.has(+dd.id))) return;
      const c=path.centroid(dd); if(!c || isNaN(c[0])) return;
      const on=isOn(v.name);
      lg.append('text').attr('x',c[0]).attr('y',c[1]).attr('text-anchor','middle')
        .attr('class', on?'clabel':'vlabel')
        .attr('paint-order','stroke').attr('stroke',P.paper)
        .attr('stroke-width',2.6).attr('stroke-linejoin','round')
        .attr('fill', on?P.signal:P.ink)
        .style('font-size', on?'11.5px':'10px')
        .text(v.name+' '+H.pct(v.rate,0));
    });
    H.in(lg, 500, 250);

    // Inline serif finding annotation (the reframe), over the sea, bottom-left.
    const finding = (scene.annotations && scene.annotations[0]) || d.finding;
    if(finding) svg.append('text').attr('class','annot').attr('x',18).attr('y',mapH-14)
      .attr('fill',P.slate).text(String(finding));

    // Sequential legend.
    const grad = svg.append('defs').append('linearGradient').attr('id',uid);
    d3.range(0,1.001,0.1).forEach(t=>grad.append('stop')
      .attr('offset',(t*100)+'%').attr('stop-color',color(t)));
    const lgnd = svg.append('g').attr('transform','translate(18,'+(Hh-30)+')');
    lgnd.append('text').attr('class','axis-title').attr('x',0).attr('y',-8)
      .text((scene.value_label||'recognition rate').toUpperCase());
    lgnd.append('rect').attr('width',220).attr('height',9).attr('rx',2)
      .attr('fill','url(#'+uid+')').attr('stroke',P.hair);
    [['0%',0],['50%',110],['100%',220]].forEach(p=>lgnd.append('text')
      .attr('class','vlabel').attr('x',p[1]).attr('y',24)
      .attr('text-anchor','middle').style('font-size','10px').text(p[0]));
    const nd = svg.append('g').attr('transform','translate(280,'+(Hh-30)+')');
    nd.append('rect').attr('width',14).attr('height',9).attr('rx',2).attr('fill',nodata).attr('stroke',P.hair);
    nd.append('text').attr('class','vlabel').attr('x',20).attr('y',8)
      .style('font-size','10px').attr('fill',P.mute).text('no data / not assessed');
  };

  d3.json(atlasUrl).then(draw).catch(e=>{
    svg.append('text').attr('x',24).attr('y',40).attr('class','annot').attr('fill',P.alarm)
      .text('Map base failed to load (needs internet for the world-atlas CDN).');
    console.error('choropleth atlas load error', e);
  });
};

// ── dumbbell ──
RENDERERS.dumbbell = function(root, d, P, H, scene){
  // Slope/dumbbell between two ranked columns. Two vertical axes:
  //   left  = metric A (e.g. total hosted), right = metric B (e.g. per 1,000).
  // Rows sit by rank; connectors join ONLY the entities present on BOTH columns
  // ("movers"). Names+values sit OUTSIDE each axis; rank ticks in the inner gutter.
  const left = d.left||[], right = d.right||[];
  const n = Math.max(left.length, right.length, 1);
  const rowH = 40, TOP = 120, BOT = 40;
  const W = 920, vbW = W;
  const Hh = TOP + n*rowH + BOT;
  const xL = 370, xR = 560;            // the two axes; gutter between them
  const y = r => TOP + (r-1)*rowH;
  const svg = H.svg(root, vbW, Hh, scene.title);

  // ── column headers ──
  svg.append('text').attr('class','axis-title').attr('x',xL).attr('y',58).attr('text-anchor','end').text(String(d.left_head||'Metric A').toUpperCase());
  if(d.left_sub) svg.append('text').attr('class','axis-title').attr('x',xL).attr('y',76).attr('text-anchor','end').style('opacity',.7).text(String(d.left_sub).toUpperCase());
  svg.append('text').attr('class','axis-title').attr('x',xR).attr('y',58).attr('text-anchor','start').text(String(d.right_head||'Metric B').toUpperCase());
  if(d.right_sub) svg.append('text').attr('class','axis-title').attr('x',xR).attr('y',76).attr('text-anchor','start').style('opacity',.7).text(String(d.right_sub).toUpperCase());

  // ── axis lines (final geometry; static) ──
  svg.append('line').attr('x1',xL).attr('x2',xL).attr('y1',y(1)-14).attr('y2',y(n)+14).attr('stroke',P.hair).attr('stroke-width',1.5);
  svg.append('line').attr('x1',xR).attr('x2',xR).attr('y1',y(1)-14).attr('y2',y(n)+14).attr('stroke',P.hair).attr('stroke-width',1.5);

  // map ISO/key → rank within each column, for connector geometry
  const lRank = {}; left.forEach(o=>{ lRank[o.key]=o.rank; });
  const rRank = {}; right.forEach(o=>{ rRank[o.key]=o.rank; });
  const movers = (d.movers||[]).filter(m=> lRank[m.key]!=null && rRank[m.key]!=null);
  const moverSet = {}; movers.forEach(m=>{ moverSet[m.key]=m; });

  // colour: highlighted entity gets accent; movers get up=amber/down=cyan; else grey
  const hueFor = (o, accentDefault) => {
    if(scene.highlight!=null){
      const hl = Array.isArray(scene.highlight)?scene.highlight:[scene.highlight];
      if(hl.indexOf(o.name)>=0 || hl.indexOf(o.key)>=0) return accentDefault||P.signal;
    }
    const m = moverSet[o.key];
    if(m) return m.dir==='up'?P.amber:P.cyan;
    if(o.standout) return accentDefault||P.signal;
    return P.grey;
  };
  const isBig = o => !!moverSet[o.key] || !!o.standout || (scene.highlight!=null && (
    (Array.isArray(scene.highlight)?scene.highlight:[scene.highlight]).some(h=>h===o.name||h===o.key)));

  // ── connectors for the shared movers (drawn FIRST so they sit behind dots) ──
  // FINAL geometry immediately; reveal via opacity only (H.in).
  const gLines = svg.append('g');
  movers.forEach((m,i)=>{
    const col = m.dir==='up'?P.amber:P.cyan;
    const ln = gLines.append('line')
      .attr('x1',xL).attr('y1',y(lRank[m.key]))
      .attr('x2',xR).attr('y2',y(rRank[m.key]))
      .attr('stroke',col).attr('stroke-width',2.4).attr('stroke-opacity',.85);
    H.in(ln, 600, 200+i*90);
  });

  // ── LEFT column: rank tick in inner gutter, name + value OUTSIDE (text-anchor end) ──
  left.forEach(o=>{
    const big = isBig(o), col = hueFor(o, P.signal);
    const g = svg.append('g');
    g.append('text').attr('class','vlabel').attr('x',xL+14).attr('y',y(o.rank)+4).attr('text-anchor','start').style('fill',P.mute).style('font-size','10px').text(o.rank);
    g.append('circle').attr('cx',xL).attr('cy',y(o.rank)).attr('r',big?6:4.5).attr('fill',col);
    const t = g.append('text').attr('class','clabel').attr('x',xL-14).attr('y',y(o.rank)+4).attr('text-anchor','end')
      .style('font-weight',big?700:500).style('fill',big?P.ink:P.slate).style('font-size','13px');
    t.append('tspan').text(o.name+'  ');
    t.append('tspan').attr('class','vlabel').style('fill',big?P.ink:P.slate).text(o.value_fmt!=null?o.value_fmt:H.fmt(o.value));
    H.in(g, 380, o.rank*32);
  });

  // ── RIGHT column: rank tick in inner gutter, value + name OUTSIDE (text-anchor start) ──
  right.forEach(o=>{
    const big = isBig(o), col = hueFor(o, P.signal);
    const g = svg.append('g');
    g.append('text').attr('class','vlabel').attr('x',xR-14).attr('y',y(o.rank)+4).attr('text-anchor','end').style('fill',P.mute).style('font-size','10px').text(o.rank);
    g.append('circle').attr('cx',xR).attr('cy',y(o.rank)).attr('r',big?6:4.5).attr('fill',col);
    const t = g.append('text').attr('class','clabel').attr('x',xR+14).attr('y',y(o.rank)+4).attr('text-anchor','start')
      .style('font-weight',big?700:500).style('fill',big?P.ink:P.slate).style('font-size','13px');
    t.append('tspan').attr('class','vlabel').style('fill',big?P.ink:P.slate).text((o.value_fmt!=null?o.value_fmt:H.fmt(o.value))+'  ');
    t.append('tspan').text(o.name);
    H.in(g, 380, o.rank*32);
  });

  // ── standout finding annotations (italic serif inline 'annot') ──
  (d.annotations||[]).forEach((a,i)=>{
    const onLeft = a.side==='left';
    const xx = onLeft ? xL-14 : xR+14;
    const yy = y(a.rank||1) - 15;
    const t = svg.append('text').attr('class','annot')
      .attr('x',xx).attr('y',yy).attr('text-anchor',onLeft?'end':'start')
      .text(a.text);
    H.in(t, 500, 900+i*200);
  });
};

// ── slope ──
// slope — two-position rank-reversal / parallel-coordinates chart (ported from
// build_flagship.py renderSimpson). One line per entity connects its left value
// to its right value; CROSSING lines reveal a rank reversal (Simpson's paradox).
// Neutral grey by default; only entities in scene.highlight take an accent.
// data: {left_label, right_label, rows:[{name,left,right,or?,sr?,note?}], y_format?('pct'|'num'), y0?}
RENDERERS.slope = function(root, d, P, H, scene){
  const rows = d.rows || [];
  const leftLab  = d.left_label  || 'Raw';
  const rightLab = d.right_label || 'Adjusted';
  const isPct = (d.y_format || 'pct') === 'pct';
  const W=720, Hh=440, m={top:26,right:150,bottom:40,left:56};
  const svg=H.svg(root, W, Hh, scene.title), iw=W-m.left-m.right, ih=Hh-m.top-m.bottom;
  const g=svg.append('g').attr('transform',`translate(${m.left},${m.top})`);

  const allV = rows.flatMap(r=>[+r.left, +r.right]);
  const x=d3.scalePoint().domain([leftLab, rightLab]).range([0,iw]).padding(.5);
  const y=d3.scaleLinear()
    .domain([ d.y0!=null ? d.y0 : 0, (d3.max(allV)||1) * 1.1 ])
    .range([ih,0]).nice();

  // axes (final, static)
  g.append('g').attr('class','axis')
    .call(d3.axisLeft(y).ticks(5).tickFormat(isPct?d3.format('.0%'):H.fmt));
  g.append('g').attr('class','axis').attr('transform',`translate(0,${ih})`)
    .call(d3.axisBottom(x));

  // faint verticals anchoring the two positions
  [leftLab, rightLab].forEach(p=>{
    g.append('line').attr('x1',x(p)).attr('x2',x(p)).attr('y1',0).attr('y2',ih)
      .attr('stroke',P.hair).attr('stroke-width',1).attr('shape-rendering','crispEdges');
  });

  const fmtV = v => isPct ? H.pct(v,0) : H.fmt(v);
  const xL=x(leftLab), xR=x(rightLab);

  rows.forEach((r,i)=>{
    const on = Array.isArray(scene.highlight)
      ? scene.highlight.indexOf(r.name)>=0
      : (scene.highlight!=null && r.name===scene.highlight);
    const col = on ? H.hue(r.name, scene.highlight, P.signal) : P.grey;
    const wgt = on ? 2.6 : 1.2;

    // FINAL geometry first; opacity-only fade-in (screenshot / backgrounded-tab safe).
    H.in(g.append('line')
      .attr('x1',xL).attr('y1',y(+r.left))
      .attr('x2',xR).attr('y2',y(+r.right))
      .attr('stroke',col).attr('stroke-width',wgt)
      .attr('stroke-opacity', on?1:0.7), 700, i*40);

    // endpoint dots at both positions
    [[xL,+r.left],[xR,+r.right]].forEach((p,pi)=>{
      H.in(g.append('circle').attr('cx',p[0]).attr('cy',y(p[1]))
        .attr('r', on?5:3).attr('fill',col), 300, 200 + i*40 + pi*120);
    });

    // name + value labels only on highlighted entities (keep neutrals quiet)
    if(on){
      // left value, anchored outside-left
      g.append('text').attr('class','vlabel')
        .attr('x',xL-8).attr('y',y(+r.left)+4).attr('text-anchor','end')
        .attr('fill',col).text(fmtV(+r.left));
      // right value + entity name, anchored outside-right
      g.append('text').attr('class','clabel')
        .attr('x',xR+10).attr('y',y(+r.right)-4).attr('fill',col).text(r.name);
      g.append('text').attr('class','vlabel')
        .attr('x',xR+10).attr('y',y(+r.right)+12).attr('fill',col).text(fmtV(+r.right));
      // rank-reversal finding annotation (italic serif), e.g. "#7 → #1"
      if(r.or!=null && r.sr!=null){
        g.append('text').attr('class','annot')
          .attr('x',xR+10).attr('y',y(+r.right)+28)
          .text('#'+r.or+' → #'+r.sr);
      } else if(r.note){
        g.append('text').attr('class','annot')
          .attr('x',xR+10).attr('y',y(+r.right)+28).text(r.note);
      }
    }
  });

  // crossing finding annotation, lower-left
  if(d.note){
    g.append('text').attr('class','annot')
      .attr('x',4).attr('y',ih-8).attr('fill',P.slate).text(d.note);
  }
};

// ── pyramid ──
RENDERERS.pyramid = function(root, d, P, H, scene){
  // Diverging population pyramid (ported from build_flagship.renderPyramid).
  // Age bands = rows; female LEFT, male RIGHT of a centre axis; symmetric linear scale.
  // d = {bands:[{age,female,male}], unit?}. female/male are numbers in the same unit
  // (e.g. millions). The female/male split IS the encoding, so it is always two-toned:
  // female = signal (cobalt), male = slate. scene.highlight === 'female' dims the male
  // side to foreground women & girls (the reference's highlightFemale mode); likewise
  // 'male' dims the female side.
  // Long-format alias: {rows:[{age_band, sex, value}]} → bands. (Demographic
  // frames arrive in this shape; without the alias the pyramid drew nothing.)
  let bandsIn = d.bands;
  if((!bandsIn || !bandsIn.length) && Array.isArray(d.rows) && d.rows.length){
    const keys=Object.keys(d.rows[0]||{});
    const ageK=keys.find(k=>/age|band|cohort|group/i.test(k));
    const sexK=keys.find(k=>/sex|gender/i.test(k));
    const valK=keys.find(k=>k!==ageK && k!==sexK && d.rows.some(r=>isFinite(parseFloat(r[k]))));
    if(ageK && sexK && valK){
      const m={}, order=[];
      d.rows.forEach(r=>{
        const a=String(r[ageK]);
        if(!m[a]){ m[a]={age:a,female:0,male:0}; order.push(a); }
        const s=String(r[sexK]).toLowerCase(), v=parseFloat(r[valK])||0;
        if(s.startsWith('f')) m[a].female+=v; else if(s.startsWith('m')) m[a].male+=v;
      });
      // oldest band on top (pyramid convention) — sort by leading number desc
      order.sort((a,b)=>(parseFloat(b)||0)-(parseFloat(a)||0));
      bandsIn=order.map(a=>m[a]);
    }
  }
  const bands = (bandsIn||[]).filter(b=>b && b.age!=null);
  const ages = bands.map(b=>String(b.age));
  const female = bands.map(b=>+b.female||0);
  const male   = bands.map(b=>+b.male||0);
  const unit = d.unit || '';                 // e.g. 'M' appended to axis ticks
  const hl = scene.highlight;
  const femAccent = (hl==null || hl==='female') ? P.signal : P.grey;
  const malAccent = (hl==null || hl==='male')   ? P.slate  : P.grey;
  const femOp = (hl==='male')   ? 0.30 : 0.92; // fill-opacity (NOT element opacity — H.in owns that)
  const malOp = (hl==='female') ? 0.30 : 0.92;

  const W=720, Hh=460, m={top:34, right:32, bottom:42, left:56};
  const svg=H.svg(root,W,Hh,scene.title), iw=W-m.left-m.right, ih=Hh-m.top-m.bottom;
  const g=svg.append('g').attr('transform','translate('+m.left+','+m.top+')');

  const maxV = (d3.max(ages.map((_,i)=>Math.max(female[i],male[i])))||1)*1.12;
  const y=d3.scaleBand().domain(ages).range([0,ih]).padding(.24);
  const x=d3.scaleLinear().domain([-maxV,maxV]).range([0,iw]);

  const tickFmt = d=>{ const a=Math.abs(d); const s=(a>=1e3?H.fmt(a):d3.format(a%1?',.1f':',')(a)); return s+unit; };
  g.append('g').attr('class','axis').attr('transform','translate(0,'+ih+')')
    .call(d3.axisBottom(x).ticks(7).tickFormat(tickFmt));

  // Centre divider
  g.append('line').attr('x1',x(0)).attr('x2',x(0)).attr('y1',0).attr('y2',ih)
    .attr('stroke',P.hair).attr('shape-rendering','crispEdges');

  ages.forEach((a,i)=>{
    // FINAL geometry drawn immediately; H.in only fades element opacity (screenshot-safe).
    const rf=g.append('rect').attr('y',y(a)).attr('height',y.bandwidth())
      .attr('x',x(-female[i])).attr('width',x(0)-x(-female[i]))
      .attr('fill',femAccent).attr('fill-opacity',femOp).attr('rx',1.5);
    const rm=g.append('rect').attr('y',y(a)).attr('height',y.bandwidth())
      .attr('x',x(0)).attr('width',x(male[i])-x(0))
      .attr('fill',malAccent).attr('fill-opacity',malOp).attr('rx',1.5);
    H.in(rf, 420, i*60); H.in(rm, 420, i*60);
    // centred age-band label — paper halo so it stays readable over the dark
    // male bar it straddles
    g.append('text').attr('class','clabel').attr('x',x(0))
      .attr('y',y(a)+y.bandwidth()/2+4).attr('text-anchor','middle')
      .attr('paint-order','stroke').attr('stroke',P.paper)
      .attr('stroke-width',3).attr('stroke-linejoin','round')
      .style('font-size','11px').text(a);
  });

  // axis unit caption (mirrors ranked_bar) — the mirrored scale needs a unit
  if(scene.value_label) g.append('text').attr('class','axis-title')
    .attr('x',iw).attr('y',ih+34).attr('text-anchor','end')
    .text(String(scene.value_label).toUpperCase());

  // Side headers
  g.append('text').attr('class','clabel').attr('x',x(-maxV*0.55)).attr('y',-12)
    .attr('text-anchor','middle').attr('fill',femAccent).text('Female');
  g.append('text').attr('class','clabel').attr('x',x(maxV*0.55)).attr('y',-12)
    .attr('text-anchor','middle').attr('fill',(hl==='female'?P.grey:malAccent)).text('Male');

  // Optional finding annotation (italic serif), voiced where the reference does.
  const ann = scene.annotation || (Array.isArray(scene.annotations)&&scene.annotations.length?scene.annotations[0]:null);
  if(ann){
    const txt = (typeof ann==='string') ? ann : (ann.text||'');
    if(txt) g.append('text').attr('class','annot')
      .attr('x', (typeof ann==='object'&&ann.side==='right')?x(maxV*0.05):x(-maxV*0.05))
      .attr('text-anchor',(typeof ann==='object'&&ann.side==='right')?'start':'end')
      .attr('y', y(ages[(typeof ann==='object'&&ann.band_index!=null)?ann.band_index:0])+y.bandwidth()/2+4)
      .text(txt);
  }
};

// ── bar_race ──
RENDERERS.bar_race = function(root, d, P, H, scene){
  const frames = (d.frames||[]).filter(f=>f && Array.isArray(f.rows) && f.rows.length);
  const K = Math.max(1, +(d.top_n||scene.top_n||10));
  const W=720, Hh=460, m={top:46,right:90,bottom:30,left:150};
  const svg=H.svg(root, W, Hh, scene.title), iw=W-m.left-m.right, ih=Hh-m.top-m.bottom;
  if(!frames.length){ svg.append('text').attr('class','annot').attr('x',W/2).attr('y',Hh/2).attr('text-anchor','middle').attr('fill',P.mute).text('No data'); return; }

  const rowH = ih / K, barH = rowH*0.74;

  // big background year mark (no dedicated CSS class → inline serif styling)
  const yearMark = svg.append('text')
    .attr('x', W-m.right-6).attr('y', m.top+ih-8).attr('text-anchor','end')
    .attr('fill', P.grey).attr('fill-opacity', 0.55)
    .style('font-family','var(--serif)').style('font-weight','700')
    .style('font-size','118px').style('letter-spacing','-.03em')
    .style('font-variant-numeric','tabular-nums');

  const g = svg.append('g').attr('transform',`translate(${m.left},${m.top})`);
  const gAxis = g.append('g').attr('class','axis');
  const gBars = g.append('g');
  if(scene.value_label) g.append('text').attr('class','axis-title')
    .attr('x',-8).attr('y',-26).text(String(scene.value_label).toUpperCase());

  // colour: default neutral grey; the one entity named in scene.highlight gets the accent.
  // (Per-row d.frames[*].rows[*].color is also honoured if the shaper supplied region colours.)
  const colourOf = (row)=> (row.color || H.hue(row.label, scene.highlight, P.signal));

  let xPrev = 1;
  function frameOf(idx){
    const f = frames[idx];
    const arr = f.rows.slice()
      .filter(r=>+r.value>0)
      .sort((a,b)=>(+b.value)-(+a.value))
      .slice(0,K)
      .map((r,i)=>({label:r.label, value:+r.value, color:r.color, rank:i}));
    return {year:f.year, arr};
  }

  function paint(idx){
    const {year, arr} = frameOf(idx);
    // ease the axis max so it doesn't jitter between frames
    const xmaxNow = d3.max(arr,r=>r.value)||1;
    xPrev = xPrev + (xmaxNow - xPrev)*0.4;
    const xmax = Math.max(xmaxNow, xPrev*0.999);
    const x = d3.scaleLinear().domain([0, xmax*1.04]).range([0, iw]);

    gAxis.attr('transform','translate(0,0)')
      .call(d3.axisTop(x).ticks(4).tickFormat(H.fmt).tickSize(-ih));
    gAxis.selectAll('.tick line').attr('stroke',P.hair).attr('stroke-dasharray','2,3');
    gAxis.select('.domain').remove();

    const yOf = r => r.rank*rowH + (rowH-barH)/2;
    const sel = gBars.selectAll('g.row').data(arr, r=>r.label);
    const ent = sel.enter().append('g').attr('class','row')
      .attr('transform', r=>`translate(0,${yOf(r)})`);
    ent.append('rect').attr('x',0).attr('height',barH).attr('rx',3);
    ent.append('text').attr('class','clabel').attr('y',barH*0.46).attr('dy','.32em');
    ent.append('text').attr('class','vlabel').attr('y',barH*0.5).attr('dy','.32em');

    const all = ent.merge(sel);
    all.attr('opacity',1).attr('transform', r=>`translate(0,${yOf(r)})`);
    all.select('rect')
      .attr('width', r=>Math.max(2, x(r.value)))
      .attr('fill', r=>colourOf(r));
    all.select('.clabel')
      .text(r=>r.label)
      .attr('x', r=> x(r.value)>120 ? 10 : -8)
      .attr('text-anchor', r=> x(r.value)>120 ? 'start':'end')
      .attr('fill', r=> x(r.value)>120 ? '#fff' : P.ink);
    all.select('.vlabel')
      .text(r=>H.fmt(r.value))
      .attr('x', r=> x(r.value)+7)
      .attr('text-anchor','start')
      .attr('fill', P.slate);
    sel.exit().attr('opacity',0).remove();

    yearMark.text(year);
  }

  // ── RELIABILITY: draw the FINAL (latest) frame immediately as the resting state.
  const lastIdx = frames.length-1;
  // warm xPrev to the final-frame max so the resting axis isn't mid-ease
  xPrev = (frameOf(lastIdx).arr[0] || {value:1}).value;
  paint(lastIdx);
  H.in(gBars, 600);        // opacity-only fade-in of the resting bars (geometry already final)
  H.in(yearMark, 600);

  // finding annotation (italic serif), if the scene names one
  if(scene.annotations && scene.annotations.length){
    g.append('text').attr('class','annot')
      .attr('x', iw).attr('y', ih+24).attr('text-anchor','end')
      .attr('fill', P.slate).text(String(scene.annotations[0]));
  }

  // ── then loop through all frames (ending on the final), unless reduced-motion.
  if(!RM && frames.length>1){
    let i = 0;                       // race restarts from the first frame
    const HOLD = 720;                // ms per frame at rest
    let lastSwitch = 0, started = null;
    // small delay so the resting final-frame paint is what a t=0 screenshot captures
    setTimeout(()=>{
      paint(0);
      const timer = d3.timer((t)=>{
        if(started===null){ started=t; lastSwitch=t; }
        if(t-lastSwitch >= HOLD){
          lastSwitch = t;
          i++;
          if(i>lastIdx){ paint(lastIdx); timer.stop(); return; }
          paint(i);
        }
      });
    }, 900);
  }
};

// ── iceberg ──
RENDERERS.iceberg = function(root, d, P, H, scene){
  // Iceberg waterline reframe: one 100%-width horizontal bar split into an
  // above-waterline segment (visible abroad) and a below-waterline mass
  // (e.g. internally displaced). A dashed waterline rule sits on the boundary;
  // serif annotations carry the reframe ("X% never crossed a border").
  // Final geometry is drawn immediately; motion is opacity-only (H.in).
  const above = d.above || {label:'Above', value:0};
  const below = d.below || {label:'Below', value:0};
  const total = (+above.value||0) + (+below.value||0) || 1;
  const W=720, Hh=420, m={top:78,right:28,bottom:84,left:28};
  const svg=H.svg(root,W,Hh,scene.title), iw=W-m.left-m.right, ih=Hh-m.top-m.bottom;
  const g=svg.append('g').attr('transform','translate('+m.left+','+m.top+')');

  const x=d3.scaleLinear().domain([0,total]).range([0,iw]);
  const barH=Math.min(132, ih*0.5), barY=(ih-barH)/2;

  // Highlight-by-colour: if scene.highlight names a segment, accent only it
  // (signal); otherwise the visible-abroad tip reads signal and the hidden
  // mass reads neutral grey — the reframe is the grey bulk below the line.
  const hasHL = scene.highlight!=null;
  const aboveCol = hasHL ? H.hue(above.label, scene.highlight, P.signal) : P.signal;
  const belowCol = hasHL ? H.hue(below.label, scene.highlight, P.signal) : P.grey;

  const segs = [
    {label:above.label, value:+above.value||0, col:aboveCol, x0:0,             below:false},
    {label:below.label, value:+below.value||0, col:belowCol, x0:(+above.value||0), below:true},
  ];

  segs.forEach((s,i)=>{
    const x0=x(s.x0), w=Math.max(0, x(s.x0+s.value)-x(s.x0));
    // final width set immediately; H.in fades opacity only
    H.in(g.append('rect').attr('x',x0).attr('y',barY).attr('width',w).attr('height',barH)
      .attr('rx',2).attr('fill',s.col), 600, s.below?260:0);
    if(s.value/total > 0.06){
      H.in(g.append('text').attr('class','vlabel').attr('fill','#fff').attr('font-weight','700')
        .attr('x',x0+w/2).attr('y',barY+barH/2+4).attr('text-anchor','middle')
        .text(H.pct(s.value/total,0)), 500, (s.below?420:160));
    }
  });

  // Dashed waterline rule on the above/below boundary. Drawn final (dash array
  // set immediately — no stroke-dashoffset reveal); H.in fades it in.
  const wlX=x(+above.value||0);
  H.in(g.append('line').attr('x1',wlX).attr('x2',wlX)
    .attr('y1',barY-26).attr('y2',barY+barH+26)
    .attr('stroke',P.ink).attr('stroke-width',1.5).attr('stroke-dasharray','4,3'), 600, 120);
  g.append('text').attr('class','axis-title').attr('x',wlX).attr('y',barY-34)
    .attr('text-anchor','middle').attr('fill',P.mute).text('WATERLINE');

  // Reframe annotation above the tip: how little "the visible part" is.
  H.in(g.append('text').attr('class','annot').attr('x',wlX-8).attr('y',barY-12)
    .attr('text-anchor','end').attr('fill',P.slate)
    .text((above.label||'abroad')+' — '+H.pct((+above.value||0)/total,0)+' →'), 600, 220);

  // The point of the chart: the hidden mass below the waterline.
  H.in(g.append('text').attr('class','annot')
    .attr('x',x((+above.value||0)+(+below.value||0)/2)).attr('y',barY+barH+34)
    .attr('text-anchor','middle').attr('fill',hasHL?P.slate:P.signal)
    .text((below.label||'below the waterline')+' — '+H.pct((+below.value||0)/total,0)+' never crossed a border'), 600, 540);

  // Footer unit / source-style caption hook via value_label.
  if(scene.value_label){
    g.append('text').attr('class','axis-title').attr('x',iw).attr('y',barY+barH+58)
      .attr('text-anchor','end').text(String(scene.value_label).toUpperCase());
  }
};

// ── projection ──
RENDERERS.projection = function(root, d, P, H, scene){
  const W=720, Hh=440, m={top:28,right:118,bottom:44,left:58};
  const svg=H.svg(root,W,Hh,scene.title), iw=W-m.left-m.right, ih=Hh-m.top-m.bottom;
  const g=svg.append('g').attr('transform',`translate(${m.left},${m.top})`);

  const series=(d.series||[]).filter(s=>s&&s.points&&s.points.length);
  const band=(d.band||[]).filter(p=>p&&p.x!=null&&p.lo!=null&&p.hi!=null).sort((a,b)=>a.x-b.x);
  const split=(d.split_year!=null)?+d.split_year:null;
  const thr=(d.threshold!=null)?+d.threshold:null;
  const fmtY = d.y_format==='pct' ? (v=>H.pct(v,0)) : (v=>H.fmt(v)+(d.y_suffix||''));

  // ── domains: x over everything, y over series + band + threshold ──
  const allPts=series.flatMap(s=>s.points);
  const xs=allPts.map(p=>p.x).concat(band.map(p=>p.x));
  const ys=allPts.map(p=>p.y)
    .concat(band.flatMap(p=>[p.lo,p.hi]))
    .concat(thr!=null?[thr]:[]);
  const xMin=d3.min(xs), xMax=d3.max(xs);
  const yMin=(d.y0!=null)?d.y0:0;
  const yMax=d3.max(ys)*1.07;
  const x=d3.scaleLinear().domain([xMin,xMax]).range([0,iw]);
  const y=d3.scaleLinear().domain([yMin,yMax]).range([ih,0]).nice();

  // ── axes + faint gridlines ──
  g.append('g').attr('class','axis').attr('transform',`translate(0,${ih})`)
    .call(d3.axisBottom(x).ticks(8).tickFormat(d3.format('d')));
  const gy=g.append('g').attr('class','axis')
    .call(d3.axisLeft(y).ticks(6).tickFormat(fmtY));
  gy.selectAll('.tick').append('line')
    .attr('x1',0).attr('x2',iw).attr('stroke',P.hair).attr('shape-rendering','crispEdges');
  if(scene.value_label) g.append('text').attr('class','axis-title')
    .attr('x',-40).attr('y',-12).text(String(scene.value_label).toUpperCase());

  // ── fit-window shade (the history the trend learned from), if given ──
  if(d.fit_lo!=null && d.fit_hi!=null){
    const x0=x(+d.fit_lo), x1=x(+d.fit_hi);
    H.in(g.append('rect').attr('x',x0).attr('width',Math.max(0,x1-x0))
      .attr('y',0).attr('height',ih).attr('fill',P.amber).attr('fill-opacity',.10),400);
    g.append('text').attr('class','axis-title').attr('x',(x0+x1)/2).attr('y',-12)
      .attr('text-anchor','middle').attr('fill',P.mute)
      .text(d.fit_label||('fitted on '+d.fit_lo+'–'+d.fit_hi));
  }

  // ── uncertainty band (between lo and hi over the projection horizon) ──
  if(band.length>1){
    const area=d3.area().x(p=>x(p.x)).y0(p=>y(p.lo)).y1(p=>y(p.hi)).curve(d3.curveMonotoneX);
    // final geometry now; opacity-only fade (fill-opacity attr is its resting value)
    H.in(g.append('path').datum(band).attr('d',area)
      .attr('fill',P.amber).attr('fill-opacity',.22).attr('stroke','none'),700,300);
  }

  // ── split marker: solid history left, dashed projection right ──
  if(split!=null && split>=xMin && split<=xMax){
    g.append('line').attr('x1',x(split)).attr('x2',x(split)).attr('y1',0).attr('y2',ih)
      .attr('stroke',P.mute).attr('stroke-width',.8).attr('stroke-dasharray','2,3').attr('opacity',.55);
    g.append('text').attr('class','axis-title').attr('x',x(split)+4).attr('y',ih-6)
      .attr('text-anchor','start').attr('fill',P.mute).text('projection →');
  }

  const lineGen=d3.line().x(p=>x(p.x)).y(p=>y(p.y)).curve(d3.curveMonotoneX);

  // ── threshold line + crossing markers ──
  if(thr!=null){
    g.append('line').attr('x1',0).attr('x2',iw).attr('y1',y(thr)).attr('y2',y(thr))
      .attr('stroke',P.ink).attr('stroke-width',1).attr('stroke-dasharray','5,4').attr('opacity',.55);
    g.append('text').attr('class','axis-title').attr('x',2).attr('y',y(thr)-6)
      .attr('fill',P.ink).text(d.threshold_label||(fmtY(thr)+' threshold'));
    (d.markers||[]).forEach((mk,i)=>{
      if(mk==null||mk.x==null) return;
      const col = scene.highlight!=null ? H.hue(mk.label,scene.highlight,SERIES[i%SERIES.length]) : SERIES[i%SERIES.length];
      if(+mk.x>=xMin && +mk.x<=xMax){
        H.in(g.append('circle').attr('cx',x(+mk.x)).attr('cy',y(thr)).attr('r',4).attr('fill',col),300,500+i*120);
        g.append('text').attr('class','annot').attr('x',x(+mk.x)).attr('y',y(thr)+17)
          .attr('text-anchor','middle').attr('fill',col).text(mk.label||'');
      }
    });
  }

  // ── crisis / event annotations dropped onto a reference series ──
  const refPts = series.length ? (series.find(s=>s.role==='history')||series[0]).points : [];
  const refAt=(xv)=>{ // nearest point's y on the reference (history) line
    if(!refPts.length) return null;
    let best=refPts[0]; for(const p of refPts) if(Math.abs(p.x-xv)<Math.abs(best.x-xv)) best=p;
    return best.y;
  };
  (d.crisis||[]).forEach(c=>{
    if(c==null||c.x==null) return;
    const cy=(c.y!=null)?+c.y:refAt(+c.x); if(cy==null) return;
    g.append('line').attr('x1',x(+c.x)).attr('x2',x(+c.x)).attr('y1',y(cy)).attr('y2',ih)
      .attr('stroke',P.mute).attr('stroke-width',.7).attr('stroke-dasharray','2,2').attr('opacity',.55);
    g.append('circle').attr('cx',x(+c.x)).attr('cy',y(cy)).attr('r',3).attr('fill',P.ink);
    g.append('text').attr('class','annot').attr('x',x(+c.x)+5).attr('y',y(cy)-6)
      .attr('text-anchor','start').text(c.label||'');
  });

  // ── the lines: history solid, projections dashed; highlight-by-colour ──
  series.forEach((s,i)=>{
    const isProj = (s.dashed===true) || (s.role==='projection');
    let col;
    if(scene.highlight!=null) col=H.hue(s.name,scene.highlight,SERIES[i%SERIES.length]);
    else if(isProj) col=SERIES[i%SERIES.length];
    else col=P.ink; // history reads as the dark spine
    const w = isProj?2.2:2.6;
    const pts=s.points.slice().sort((a,b)=>a.x-b.x);
    // FINAL geometry first (full dashed pattern set as a resting attr); H.in fades opacity only
    const path=g.append('path').datum(pts).attr('fill','none')
      .attr('stroke',col).attr('stroke-width',w)
      .attr('stroke-linejoin','round').attr('stroke-linecap','round')
      .attr('d',lineGen);
    if(isProj) path.attr('stroke-dasharray','6,5');
    H.in(path, 800, i*140);
    // end-of-line label (replaces a legend)
    const last=pts[pts.length-1];
    H.in(g.append('text').attr('class','clabel').attr('x',x(last.x)+7).attr('y',y(last.y)+4)
      .attr('fill',col).style('font-size','12px').text(s.name||''), 400, 300+i*140);
  });
};

// ── sankey_corridors ──
RENDERERS.sankey_corridors = function(root, d, P, H, scene){
  const nodesIn = (d.nodes||[]), linksIn = (d.links||[]);
  if(!nodesIn.length || !linksIn.length){ root.append('div').attr('class','caption').text('[sankey_corridors: no data]'); return; }

  // ── layout box (Sankey needs vertical room for stacked rows) ──
  const W=720, Hh=520, m={top:30,right:8,bottom:14,left:8};
  const svg=H.svg(root, W, Hh, scene.title);
  const iw=W-m.left-m.right, ih=Hh-m.top-m.bottom;
  const g=svg.append('g').attr('transform',`translate(${m.left},${m.top})`);

  // ── build the sankey graph (numeric source/target indices into nodesIn) ──
  const sankey = d3.sankey()
    .nodeWidth(13).nodePadding(9)
    .nodeSort(null)                                  // keep insertion order (largest-first, top→bottom)
    .extent([[150,0],[iw-150,ih]]);
  const graph = sankey({
    nodes: nodesIn.map(n=>Object.assign({}, n)),
    links: linksIn.map(l=>Object.assign({}, l)),
  });

  // derive side from layout when not supplied: x0 near left edge ⇒ origin
  const minX0 = d3.min(graph.nodes, n=>n.x0);
  graph.nodes.forEach(n=>{ if(n.side==null) n.side = (n.x0<=minX0+1)?'orig':'host'; });

  // ── colour links by SOURCE node, highlight-by-colour ──
  // Default: biggest origin = signal, rest = grey. With scene.highlight, only the
  // named origin(s) accent; the bundled "other" band always renders neutral grey.
  const origins = graph.nodes.filter(n=>n.side==='orig' && !n.other)
    .sort((a,b)=>(b.value||0)-(a.value||0));
  const rankOfName = new Map(origins.map((n,i)=>[n.name,i]));
  function srcColor(srcNode){
    if(srcNode.other) return P.grey;
    if(scene.highlight!=null) return H.hue(srcNode.name, scene.highlight, P.signal);
    // no explicit highlight: lead colour for the single biggest origin, grey otherwise
    return rankOfName.get(srcNode.name)===0 ? P.signal : P.grey;
  }

  // ── column headers (mono caps, axis-title class) ──
  const origNode = graph.nodes.find(n=>n.side==='orig');
  g.append('text').attr('class','axis-title').attr('x', origNode? origNode.x0 : 0).attr('y',-12).text('ORIGIN');
  g.append('text').attr('class','axis-title').attr('text-anchor','end').attr('x',iw).attr('y',-12).text('HOST COUNTRY');

  // ── links: draw FINAL geometry now; fade in (opacity only via H.in) ──
  const linkGen = d3.sankeyLinkHorizontal();
  graph.links.sort((a,b)=>(b.value||0)-(a.value||0));
  graph.links.forEach((lk,i)=>{
    const isOther = !!(lk.source.other || lk.target.other);
    const col = isOther ? P.grey : srcColor(lk.source);
    const path = g.append('path')
      .attr('d', linkGen(lk))
      .attr('fill','none')
      .attr('stroke', col)
      .attr('stroke-opacity', isOther ? 0.30 : 0.50)   // partial transparency via ATTR (H.in owns 'opacity')
      .attr('stroke-width', Math.max(1, lk.width));
    path.append('title').text(
      (lk.source.name||'')+' → '+(lk.target.name||'')+': '+H.fmt(lk.value)+' refugees');
    H.in(path, 520, 120 + i*55);                        // largest-first stagger
  });

  // ── nodes: rects (final geometry now) ──
  graph.nodes.forEach(n=>{
    const col = n.other ? P.grey : (n.side==='orig' ? srcColor(n) : P.slate);
    g.append('rect')
      .attr('x', n.x0).attr('y', n.y0)
      .attr('width', n.x1-n.x0).attr('height', Math.max(1, n.y1-n.y0))
      .attr('rx', 2)
      .attr('fill', col).attr('fill-opacity', 0.92);
  });

  // ── label the biggest nodes; origin labels LEFT of rect, host labels RIGHT ──
  // threshold: only nodes carrying a visible share, to avoid clutter on thin rows
  const maxNodeVal = d3.max(graph.nodes, n=>n.value)||1;
  const labelMin = maxNodeVal * 0.06;
  graph.nodes.forEach(n=>{
    if(!n.other && n.value < labelMin) return;          // only the biggest nodes
    const left = n.side==='orig';
    const cy = (n.y0+n.y1)/2;
    g.append('text')
      .attr('class','clabel')
      .attr('x', left ? n.x0-6 : n.x1+6)
      .attr('y', cy-2).attr('dy','0.32em')
      .attr('text-anchor', left ? 'end' : 'start')
      .attr('fill', n.other ? P.mute : P.ink)
      .style('font-size','11px')
      .text(n.name);
    g.append('text')
      .attr('class','vlabel')
      .attr('x', left ? n.x0-6 : n.x1+6)
      .attr('y', cy+9)
      .attr('text-anchor', left ? 'end' : 'start')
      .attr('fill', P.mute).style('font-size','9.5px')
      .text(H.fmt(n.value));
  });

  // ── finding annotation (italic serif) for the biggest REAL corridor ──
  // (skip the bundled "all other corridors" band — it is never the headline)
  const top = graph.links.find(lk=>!(lk.source.other||lk.target.other));
  if(top){
    g.append('text').attr('class','annot')
      .attr('x', iw/2).attr('y', ih+8).attr('text-anchor','middle')
      .text('Largest single corridor: '+top.source.name+' → '+top.target.name+' ('+H.fmt(top.value)+')');
  }
};

// ── kpi_grid ──
RENDERERS.kpi_grid = function(root, d, P, H, scene){
  // KPI grid — responsive grid of cards, each a big serif number (cobalt) + label
  // + optional signed delta (amber up / alarm down). HTML divs, NOT svg, for crisp text.
  root.classed('bare', true);
  const cards = (d && d.cards) || [];
  const cols = (d && d.columns) || Math.min(cards.length || 1, cards.length >= 4 ? 4 : (cards.length || 1));
  // grid wrapper — fonts/colours from CSS vars + P only; existing classes are SVG-fill,
  // so cards are inline-styled HTML mirroring the page-level .stat-card visual idea.
  const grid = root.append('div')
    .style('display', 'grid')
    .style('grid-template-columns', `repeat(auto-fit, minmax(${cards.length > 3 ? 160 : 200}px, 1fr))`)
    .style('gap', '1.1rem')
    .style('padding', '4px 0 6px');
  cards.forEach((c, i) => {
    const accent = (scene.highlight != null && c.label != null && H.hue(c.label, scene.highlight) !== P.grey)
      ? H.hue(c.label, scene.highlight) : P.signal;
    const card = grid.append('div')
      .style('border-top', `2px solid ${P.hair}`)
      .style('padding-top', '.85rem');
    // big serif number (cobalt by default; accent if highlighted)
    const valTxt = (c.value_fmt != null && c.value_fmt !== '')
      ? c.value_fmt
      : (typeof c.value === 'number' ? H.fmt(c.value) : String(c.value == null ? '' : c.value));
    card.append('div')
      .style('font-family', 'var(--serif)')
      .style('font-weight', '700')
      .style('font-size', 'clamp(2rem,4.4vw,3rem)')
      .style('line-height', '1')
      .style('letter-spacing', '-.02em')
      .style('font-variant-numeric', 'tabular-nums')
      .style('color', accent)
      .text(valTxt);
    // optional signed delta — amber up / alarm down (▲/▼ are typographic glyphs, not emoji)
    if (c.delta != null && c.delta !== '') {
      let dir = c.delta_dir;
      if (dir == null) {
        const dn = (typeof c.delta === 'number') ? c.delta : parseFloat(String(c.delta).replace(/[^0-9.\-]/g, ''));
        dir = (isFinite(dn) && dn < 0) ? 'down' : 'up';
      }
      const dcol = dir === 'down' ? P.alarm : P.amber;
      const arrow = dir === 'down' ? '▼' : '▲';
      const dtxt = (typeof c.delta === 'number')
        ? (c.delta > 0 ? '+' : '') + H.fmt(c.delta)
        : String(c.delta);
      card.append('div')
        .style('font-family', 'var(--mono)')
        .style('font-size', '.82rem')
        .style('font-weight', '500')
        .style('margin-top', '.4rem')
        .style('color', dcol)
        .style('font-variant-numeric', 'tabular-nums')
        .html(`<span style="font-size:.78em">${arrow}</span> ${dtxt.replace(/&/g,'&amp;').replace(/</g,'&lt;')}`);
    }
    // label
    card.append('div')
      .style('font-family', 'var(--sans)')
      .style('font-size', '.9rem')
      .style('color', P.slate)
      .style('margin-top', '.45rem')
      .style('max-width', '32ch')
      .style('line-height', '1.35')
      .text(c.label || '');
    // optional one-line context / sub
    if (c.sub) {
      card.append('div')
        .style('font-family', 'var(--sans)')
        .style('font-size', '.78rem')
        .style('color', P.mute)
        .style('margin-top', '.25rem')
        .text(c.sub);
    }
    // final geometry already painted; opacity-only staggered fade-in (screenshot-safe)
    H.in(card, 420, i * 70);
  });
  // optional finding annotation under the grid (italic serif), like the reference annots
  if (scene.annotations && scene.annotations.length) {
    const a = root.append('div')
      .style('font-family', 'var(--serif)')
      .style('font-style', 'italic')
      .style('font-size', '.95rem')
      .style('color', P.slate)
      .style('margin-top', '1.1rem')
      .text(scene.annotations[0]);
    H.in(a, 420, cards.length * 70 + 120);
  }
};

// count_up is an alias of stat (single big number, count-up motion)
RENDERERS.count_up = RENDERERS.stat;

// ── Driver: build the page from DATA ──
(function(){
  document.title = DATA.title || 'India healthcare data story';
  const set=(id,txt)=>{const el=document.getElementById(id); if(el) el.textContent=txt||'';};
  set('kicker', DATA.kicker); set('title', DATA.title); set('lede', DATA.lede);
  // stat cards
  if(DATA.stats && DATA.stats.length){
    const sc=document.getElementById('stat-cards'); sc.hidden=false;
    DATA.stats.forEach(s=>{ const c=document.createElement('div'); c.className='stat-card';
      c.innerHTML='<div class="n"></div><div class="l"></div>';
      c.querySelector('.n').textContent=s.value; c.querySelector('.l').textContent=s.label; sc.appendChild(c); });
  }
  // scenes
  const host=document.getElementById('scenes');
  (DATA.scenes||[]).forEach((sc,i)=>{
    const sec=document.createElement('section'); sec.className='scene'; sec.id='scene-'+i;
    sec.innerHTML='<p class="eyebrow"></p><h2></h2><p class="scene-lede"></p><div class="figure"></div><p class="caption"></p>';
    sec.querySelector('.eyebrow').textContent=sc.eyebrow||'';
    sec.querySelector('h2').textContent=sc.title||'';
    sec.querySelector('.scene-lede').textContent=sc.lede||'';
    sec.querySelector('.caption').textContent=sc.caption||'';
    if(!sc.eyebrow) sec.querySelector('.eyebrow').remove();
    if(!sc.lede) sec.querySelector('.scene-lede').remove();
    if(!sc.caption) sec.querySelector('.caption').remove();
    host.appendChild(sec);
    const fn=RENDERERS[sc.type];
    const fig=d3.select(sec).select('.figure');
    if(fn){ try{ fn(fig, sc.data||{}, P, H, sc); }catch(e){ fig.append('div').attr('class','caption').text('[render error: '+sc.type+']'); console.error(sc.type,e);} }
    else { fig.append('div').attr('class','caption').text('[unknown chart type: '+sc.type+']'); }
  });
  // methodology
  set('method-body', DATA.methodology || '');
  set('method-src', DATA.source || 'Source: Virtue Foundation India healthcare dataset (DAIS-for-Good 2026). AI-composed via Databricks Mosaic agent.');
  if(!DATA.methodology){ const m=document.getElementById('method-body'); if(m) m.remove(); }
  // ── One-time scroll reveal ──
  // Below-the-fold scenes pause their entrance animation (.fx-wait) and play it
  // ONCE on first viewport entry (unobserve → can never re-trigger while
  // scrolling up/down). Same-tick class application = no flash; reduced-motion
  // and no-IntersectionObserver environments skip the pause entirely, and
  // beforeprint force-reveals everything so PDF/print exports stay complete.
  if(!RM && 'IntersectionObserver' in window){
    const secs=[...document.querySelectorAll('.scene')];
    const io=new IntersectionObserver(ents=>{
      ents.forEach(en=>{ if(en.isIntersecting){ en.target.classList.remove('fx-wait'); io.unobserve(en.target); } });
    },{threshold:0.12});
    secs.forEach(sec=>{
      if(sec.getBoundingClientRect().top > innerHeight*0.92){ sec.classList.add('fx-wait'); io.observe(sec); }
    });
    addEventListener('beforeprint',()=>secs.forEach(s=>s.classList.remove('fx-wait')));
  }
})();
</script>
</body></html>
"""


# ════════════════════════════════════════════════════════════════════════
# Python side — shape each scene's data slice from a DataFrame, assemble DATA.
# ════════════════════════════════════════════════════════════════════════

def _num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


_YEARISH_NAME = re.compile(r"^(year|yr|yyyy|date|month|mth|period|pop_year|gdp_year)s?$", re.I)


def _is_yearish(df: pd.DataFrame, col: str) -> bool:
    """A column that is a calendar year/date — never a chart VALUE. Genie often
    returns the real metric columns as STRINGS, leaving the year as the only
    true-numeric column; without this guard the bars chart the year (all 2,024)."""
    if _YEARISH_NAME.match(str(col)):
        return True
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if not len(s):
        return False
    return bool((s % 1 == 0).all() and s.between(1900, 2100).all())


def _coercible_num_cols(df: pd.DataFrame) -> list:
    """Columns usable as numerics — true-numeric dtype OR string columns where
    >=80% of values coerce (Genie string-typed metrics)."""
    out = []
    for c in df.columns:
        s = pd.to_numeric(df[c], errors="coerce")
        if len(s) and float(s.notna().mean()) >= 0.8:
            out.append(c)
    return out


def _shape_scene_data(df: pd.DataFrame | None, scene: dict) -> dict:
    """Compute a scene's `data` slice. If the scene carries inline `data`,
    use it verbatim (agent precomputed stats SQL can't do)."""
    if scene.get("data") is not None:
        return scene["data"]
    if df is None or df.empty:
        return {}
    t = scene["type"]
    mp = scene.get("mapping", {}) or {}

    num_cols = _coercible_num_cols(df)

    def first_cat():
        return next((c for c in df.columns if c not in num_cols), df.columns[0])

    def first_num():
        # prefer a non-year metric column; fall back to any coercible numeric
        for c in num_cols:
            if not _is_yearish(df, c):
                return c
        return num_cols[0] if num_cols else df.columns[-1]

    def value_col_for(requested: str | None) -> str:
        """Honor the request unless it is year-like AND a real metric column
        exists — charting a year as the value is always a bug."""
        col = requested or first_num()
        if col in df.columns and _is_yearish(df, col):
            alt = next((c for c in num_cols if c != col and not _is_yearish(df, c)), None)
            if alt is not None:
                logger.warning("compose_infographic: value column %r is year-like; using %r instead", col, alt)
                return alt
        return col

    if t == "ranked_bar":
        label = mp.get("label_col") or first_cat()
        value = value_col_for(mp.get("value_col"))
        top_n = int(scene.get("top_n", mp.get("top_n", 10)))
        sub = df[[label, value]].dropna().copy()
        sub[value] = pd.to_numeric(sub[value], errors="coerce")
        sub = sub.dropna().sort_values(value, ascending=False).head(top_n)
        return {"rows": [{"label": str(r[label]), "value": float(r[value]),
                          "label_fmt": _fmt_number(r[value])} for _, r in sub.iterrows()]}

    if t == "line_multi":
        x = mp.get("x_col") or next((c for c in df.columns if _is_yearish(df, c)), df.columns[0])
        y = value_col_for(mp.get("y_col") if mp.get("y_col") != x else None)
        if y == x:
            y = first_num()
        s = mp.get("series_col")
        out = []
        if s and s in df.columns:
            for name, grp in df[[x, y, s]].dropna().groupby(s):
                gx, gy = _num(grp, x), _num(grp, y)
                pts = sorted([{"x": float(a), "y": float(b)} for a, b in zip(gx, gy)
                              if pd.notna(a) and pd.notna(b)], key=lambda p: p["x"])
                if pts:
                    out.append({"name": str(name), "points": pts})
            out.sort(key=lambda ss: -(ss["points"][-1]["y"] if ss["points"] else 0))
        else:
            sx, sy = _num(df, x), _num(df, y)
            pts = sorted([{"x": float(a), "y": float(b)} for a, b in zip(sx, sy)
                          if pd.notna(a) and pd.notna(b)], key=lambda p: p["x"])
            out = [{"name": mp.get("y_label", y), "points": pts}]
        return {"series": out, "y_format": mp.get("y_format", "num"), "y0": mp.get("y0")}

    if t in ("stacked_area", "stacked_area_share"):
        x = mp.get("x_col") or df.columns[0]
        keys = mp.get("keys") or [c for c in df.columns if c != x and pd.api.types.is_numeric_dtype(df[c])]
        rows = []
        for _, r in df.sort_values(x).iterrows():
            row = {"x": float(r[x])}
            for k in keys:
                row[k] = float(pd.to_numeric(pd.Series([r[k]]), errors="coerce").iloc[0] or 0)
            rows.append(row)
        return {"keys": list(keys), "rows": rows}

    if t == "lorenz_gini":
        # Expect df with a value column; compute Lorenz arrays + Gini here.
        value = mp.get("value_col") or first_num()
        vals = sorted(float(v) for v in _num(df, value).dropna() if v > 0)
        n = len(vals)
        if n == 0:
            return {"lorenz_x": [0, 1], "lorenz_y": [0, 1], "gini": 0.0}
        total = sum(vals)
        cum, lx, ly = 0.0, [0.0], [0.0]
        for i, v in enumerate(vals, 1):
            cum += v
            lx.append(i / n)
            ly.append(cum / total)
        # Gini = 1 - sum((y_i + y_{i-1}) * (x_i - x_{i-1}))
        gini = 1 - sum((ly[i] + ly[i - 1]) * (lx[i] - lx[i - 1]) for i in range(1, len(lx)))
        return {"lorenz_x": lx, "lorenz_y": ly, "gini": round(gini, 3)}

    if t == "stat":
        value = mp.get("value_col") or first_num()
        col = pd.to_numeric(df[value], errors="coerce")
        big = float(col.iloc[0]) if len(df) == 1 else float(col.sum())
        return {"value": big, "context": scene.get("context", "")}

    # Fallback: hand the whole (small) frame to the renderer as records.
    return {"rows": df.head(50).to_dict(orient="records")}


def _sanitize_json(obj):
    """NaN/Inf → None recursively. json.dumps would emit bare NaN (a JS literal
    the renderers then print as 'NaN'); null is filtered by every renderer."""
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return None
    return obj


def _assemble(*, title: str, kicker: str, lede: str, scenes: list,
              scene_data: list, stats: list, methodology: str, source: str) -> str:
    data = {
        "title": title, "kicker": kicker, "lede": lede,
        "stats": stats or [],
        "methodology": methodology or "",
        "source": source or "",
        "scenes": [
            {
                "type": s["type"],
                "eyebrow": s.get("eyebrow", ""),
                "title": s.get("title", ""),
                "lede": s.get("lede", ""),
                "caption": s.get("caption", ""),
                "highlight": s.get("highlight"),
                "value_label": s.get("value_label", ""),
                "top_n": s.get("top_n"),
                "annotations": s.get("annotations", []),
                "data": d,
            }
            for s, d in zip(scenes, scene_data)
        ],
    }
    return _SCAFFOLD.replace('"__DATA__"', json.dumps(_sanitize_json(data), ensure_ascii=False))


def _normalize_scenes(*, scenes, template, label_col, value_col, x_col, y_col,
                      series_col, value_unit, top_n, variable_name) -> list:
    """Back-compat: if no scenes given, synthesize one from the legacy
    single-template params."""
    if scenes:
        return scenes
    arch = _LEGACY_TEMPLATE.get(template, None)
    if arch is None or template == "auto":
        arch = None  # signal auto-pick downstream
    mapping = {}
    if label_col:
        mapping["label_col"] = label_col
    if value_col:
        mapping["value_col"] = value_col
    if x_col:
        mapping["x_col"] = x_col
    if y_col:
        mapping["y_col"] = y_col
    if series_col:
        mapping["series_col"] = series_col
    return [{
        "type": arch or "_auto",
        "variable_name": variable_name,
        "mapping": mapping,
        "value_label": value_unit,
        "top_n": top_n,
    }]


def _auto_archetype(df: pd.DataFrame) -> str:
    n_rows, n_cols = df.shape
    if n_rows == 1:
        return "stat"
    cols = list(df.columns)
    year_col = next((c for c in cols if re.fullmatch(r"(year|yr|date)", str(c), re.I)), None)
    if year_col is None:
        for c in cols:
            if pd.api.types.is_numeric_dtype(df[c]):
                v = df[c].dropna()
                if len(v) and v.min() >= 1900 and v.max() <= 2100:
                    year_col = c
                    break
    num = [c for c in cols if c != year_col and pd.api.types.is_numeric_dtype(df[c])]
    if year_col and num:
        return "line_multi"
    return "ranked_bar"


# ════════════════════════════════════════════════════════════════════════
# Tool factory
# ════════════════════════════════════════════════════════════════════════

def build_compose_infographic_tool(*, workspace_client: Any, variable_store_cls: Callable, app_url: str):
    """Factory mirroring the v3 build_render_chart_tool signature."""

    @tool
    def compose_infographic(
        title: Annotated[str, "Short, sober story title. No emoji, no clickbait. Time scope in the title when the data has one."],
        scenes: Annotated[
            list,
            "Ordered list of scene dicts → a multi-panel data story (one scene = a single infographic). "
            "Each scene: {type, variable_name?, mapping?, data?, eyebrow?, title?, lede?, caption?, highlight?, "
            "value_label?, top_n?, annotations?}. `type` ∈ ranked_bar, line_multi, stacked_area, "
            "stacked_area_share, lorenz_gini, forest_ci, heatmap_matrix, bubble_scatter, choropleth, dumbbell, "
            "slope, pyramid, bar_race, iceberg, projection, kpi_grid, count_up, sankey_corridors, stat. "
            "Give a scene `data` inline "
            "for stats SQL can't do (Gini value, OLS fit, logistic odds-ratios+CIs); otherwise give "
            "`variable_name`+`mapping` and the tool shapes the slice from the stored DataFrame. "
            "A `stat` scene's data MUST carry a numeric `value` (or `value_fmt`); use `headline` "
            "only for a words-as-stat callout. For bubble_scatter give points as "
            "{name,gdp,per1000,hosted,region}. DATA-SHAPE CONTRACTS: heatmap_matrix is ONLY for a "
            "rate matrix — {origins:[{iso,name}], dests:[{iso,name}], cells:[{o,d,trr}]}; "
            "age-sex/demographic breakdowns use `pyramid` ({bands:[{age,female,male}]} or long-format "
            "{rows:[{age_band,sex,value}]}), NEVER heatmap_matrix. If your data doesn't fit an "
            "archetype's contract, pick a simpler archetype (ranked_bar/line_multi) instead of "
            "forcing it. line_multi AUTO-handles axis + label hygiene: it zooms the y-axis to the "
            "data when the series sit far above zero (with an explicit 'y-axis zoomed' note; pass "
            "data.y0=0 to force a zero baseline), dodges converging end-of-line labels, and with "
            ">8 series labels only the important ones — do NOT pre-trim series to avoid overlap. "
            "Call find_skill(\"infographic scene recipes\") for archetype selection + "
            "editorial-voice guidance.",
        ] = None,
        variable_name: Annotated[str, "Default stored DataFrame for scenes that don't name their own."] = "",
        lede: Annotated[str, "One- or two-sentence editorial lede under the title. Human framing first."] = "",
        kicker: Annotated[str, "Short eyebrow above the title (e.g. 'India · Healthcare access')."] = "",
        stats: Annotated[list, "Optional hero stat cards: list of {value, label}. Lead with the reframe number."] = None,
        methodology: Annotated[str, "Methodology paragraph (period, definitions, controls, limitations). Builds trust."] = "",
        source_note: Annotated[str, "Source footer. Defaults to the Virtue Foundation India healthcare dataset line."] = "",
        # ── legacy single-template params (back-compat; hidden from the model) ──
        template: Annotated[str, "Legacy — unused; prefer `scenes`."] = "auto",
        label_col: Annotated[str, "Legacy — unused."] = "",
        value_col: Annotated[str, "Legacy — unused."] = "",
        x_col: Annotated[str, "Legacy — unused."] = "",
        y_col: Annotated[str, "Legacy — unused."] = "",
        series_col: Annotated[str, "Legacy — unused."] = "",
        value_unit: Annotated[str, "Legacy — unused."] = "",
        eyebrow: Annotated[str, "Legacy — unused."] = "",
        top_n: Annotated[int, "Rows for ranked_bar."] = 10,
        kpi_context: Annotated[str, "Legacy — unused."] = "",
        store: Annotated[Any, InjectedStore()] = None,
        config: RunnableConfig = None,
    ) -> str:
        """Compose a single-file D3 data-story infographic from stored DataFrame(s).

        Returns compact JSON {"status":"ok","infographic_id":..,"url":..,"scene_count":..}.
        The frontend auto-opens the artifact from this JSON — reference the infographic by
        TITLE in prose; never paste the raw JSON, the url, or the Volumes path.
        """
        try:
            cfg = config or {}
            configurable = cfg.get("configurable", {}) or {}
            user_id = configurable.get("user_id", "default_user")
            thread_id = configurable.get("thread_id", "default_thread")
            vs = variable_store_cls(store=store, user_id=user_id, thread_id=thread_id)

            norm = _normalize_scenes(
                scenes=scenes, template=template, label_col=label_col, value_col=value_col,
                x_col=x_col, y_col=y_col, series_col=series_col, value_unit=value_unit,
                top_n=top_n, variable_name=variable_name,
            )
            if not norm:
                return _compact_error(error_type="bad_spec", message="No scenes and no legacy template params provided.")

            # Resolve + shape each scene's data slice.
            scene_data = []
            df_cache: dict[str, Any] = {}
            for sc in norm:
                if sc.get("data") is not None:
                    scene_data.append(_shape_scene_data(None, sc))
                    continue
                vn = sc.get("variable_name") or variable_name
                if not vn:
                    return _compact_error(error_type="bad_spec",
                                          message=f"Scene '{sc.get('type')}' has neither inline data nor a variable_name.")
                if vn not in df_cache:
                    df_cache[vn] = vs.get(vn)
                df = df_cache[vn]
                if df is None:
                    return _compact_error(error_type="store_error", message=f"Variable '{vn}' not found in store.")
                if sc.get("type") in (None, "_auto"):
                    sc["type"] = _auto_archetype(df)
                if sc["type"] not in _ARCHETYPES:
                    return _compact_error(error_type="bad_template",
                                          message=f"Unknown scene type '{sc['type']}'. Valid: {sorted(_ARCHETYPES)}")
                scene_data.append(_shape_scene_data(df, sc))

            stat_cards = [{"value": s.get("value", ""), "label": s.get("label", "")} for s in (stats or [])]
            html_str = _assemble(
                title=title, kicker=kicker or eyebrow, lede=lede, scenes=norm,
                scene_data=scene_data, stats=stat_cards,
                methodology=methodology, source=source_note,
            )

            iid = _infographic_id(title, norm)
            html_path = f"{_VOLUME_ROOT}/{iid}.html"
            try:
                workspace_client.files.create_directory(_VOLUME_ROOT)
            except Exception:
                pass
            workspace_client.files.upload(html_path, BytesIO(html_str.encode("utf-8")), overwrite=True)

            url = f"{app_url.rstrip('/')}/api/infographics/{iid}" if app_url else f"/api/infographics/{iid}"
            return json.dumps({
                "status": "ok", "infographic_id": iid, "title": title,
                "scene_count": len(norm), "scene_types": [s["type"] for s in norm], "url": url,
            }, separators=(",", ":"))
        except Exception as e:
            logger.exception("compose_infographic failed")
            return _compact_error(error_type="render_error", message=str(e)[:200])

    return compose_infographic


# ── Local validation entrypoint (no Databricks SDK) ──────────────────────
def _render_local(*, title="Test", kicker="", lede="", scenes, stats=None,
                  methodology="", source="") -> str:
    """Direct render for pytest / local preview. `scenes` carry inline `data`
    (no DataFrame shaping). Returns the HTML string."""
    scene_data = [_shape_scene_data(None, s) for s in scenes]
    return _assemble(title=title, kicker=kicker, lede=lede, scenes=scenes,
                     scene_data=scene_data, stats=stats or [], methodology=methodology, source=source)
