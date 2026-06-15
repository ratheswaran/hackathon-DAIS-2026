"""find_skill — Neo4j llm-wiki knowledge-graph traversal.

This is the ONE thing this orchestrator changes versus the production
hackathon-orchestrator: it replaces the filesystem skills folder entirely with
a graph the agent traverses. There is NO skill-file reading.

``find_skill(query)`` runs the knowledge graph (``brain/kg_retrieve.py::
kg_search``): it seeds on the most relevant nodes (vector + fulltext over node
content), expands ONE hop along the answer-path relations (ROUTES_TO / ANSWERS /
COMPUTES / HONORS / VISUALIZED_BY / PRODUCED_BY / SURFACES / ABOUT …), and
returns a PLAN — which Genie space to query, the verbatim SQL pattern, the
gotchas to honor, the metric, the chart/deck recipe + which tool to call, and
the "why" insight. Every node carries its own self-sufficient content, so the
agent never opens a file.

Graph corpus = the skills + the EDA/findings analysis, disassembled into an
llm-wiki-as-graph (Domain/GenieSpace/Table/Column/Metric/Rule/SqlPattern/
ChartRecipe/DesignRule/SlideType/DeckGuide/Tool/Finding/Question/Country/Asset)
with typed relationships. Loaded into Neo4j (Aura Free) by kg/merge_load.py.

Embeddings: the query is embedded with the SAME Databricks FM endpoint the graph
was ingested with (``databricks-gte-large-en``, 1024-dim) — no torch in the
serving image, one embed call per query.

Neo4j credentials come from env vars (injected at deploy from a secret scope,
mirroring the SAP GraphRAG reference): ``NEO4J_URI``, ``NEO4J_USER``,
``NEO4J_PASSWORD``, ``NEO4J_DATABASE``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Callable, Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_driver = None
_driver_lock = threading.Lock()
_embed_fn_singleton: Optional[Callable[[str], list]] = None
_embed_lock = threading.Lock()


def _get_driver():
    """Lazy, process-wide Neo4j driver built from env credentials."""
    global _driver
    if _driver is not None:
        return _driver
    with _driver_lock:
        if _driver is None:
            from brain.db import Neo4j  # vendored brain
            _driver = Neo4j()  # reads NEO4J_URI/USER/PASSWORD/DATABASE from env
            logger.info("find_skill: Neo4j driver initialized (%s)",
                        os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    return _driver


def _build_embed_fn(embedding_endpoint: str) -> Callable[[str], list]:
    """Query embedder. Prefer DatabricksEmbeddings (ambient serving auth); fall
    back to the brain's stdlib HTTP path when the integration isn't importable."""
    try:
        from databricks_langchain import DatabricksEmbeddings
        emb = DatabricksEmbeddings(endpoint=embedding_endpoint)
        logger.info("find_skill: query embedder = DatabricksEmbeddings(%s)", embedding_endpoint)
        return lambda q: emb.embed_query(q)
    except Exception as e:  # pragma: no cover
        logger.warning("find_skill: DatabricksEmbeddings unavailable (%s); using brain.embed HTTP path", e)
        os.environ.setdefault("BRAIN_EMBED_BACKEND", "databricks")
        os.environ.setdefault("BRAIN_EMBED_ENDPOINT", embedding_endpoint)
        from brain import embed
        return lambda q: embed.encode_one(q)


def _get_embed_fn(embedding_endpoint: str) -> Callable[[str], list]:
    global _embed_fn_singleton
    if _embed_fn_singleton is not None:
        return _embed_fn_singleton
    with _embed_lock:
        if _embed_fn_singleton is None:
            _embed_fn_singleton = _build_embed_fn(embedding_endpoint)
    return _embed_fn_singleton


def build_find_skill_tool(
    *,
    embedding_endpoint: str = "databricks-gte-large-en",
    result_k: int = 6,
    workspace_client: Any = None,
    app_url: Optional[str] = None,
    volume_dir: str = "/Volumes/workspace/ai_ops/agent_scratch/skill_graphs",
    render_graph: bool = True,
    embed_fn: Optional[Callable[[str], list]] = None,
):
    """Build the ``find_skill`` tool.

    Args:
        embedding_endpoint: Databricks FM embeddings endpoint used to embed the
            query (must match the endpoint the graph was ingested with).
        result_k: Number of seed nodes (the graph then expands 1 hop for the plan).
        workspace_client: SP WorkspaceClient for uploading the per-query graph
            HTML to a UC Volume (best-effort; None disables graph upload).
        app_url: App base URL used to build a clickable graph link.
        volume_dir: UC Volume directory for the per-query graph HTML.
        render_graph: When True (default) + a workspace_client is present, upload
            a per-query traversal-graph HTML and return its link.
        embed_fn: Optional query embedder override (used by the local e2e harness).
    """

    def _embed(q: str) -> list:
        if embed_fn is not None:
            return embed_fn(q)
        return _get_embed_fn(embedding_endpoint)(q)

    def _maybe_upload_graph(res, query: str) -> Optional[str]:
        if not (render_graph and workspace_client is not None):
            return None
        try:
            import io
            html = _subgraph_html(res, query)
            gid = hashlib.md5(f"{query}{time.time()}".encode()).hexdigest()[:12]
            path = f"{volume_dir.rstrip('/')}/skillgraph_{gid}.html"
            try:
                workspace_client.files.create_directory(volume_dir)
            except Exception:
                pass
            workspace_client.files.upload(path, io.BytesIO(html.encode("utf-8")), overwrite=True)
            return f"{app_url.rstrip('/')}/api/skill_graph/{gid}.html" if app_url else path
        except Exception as e:
            logger.warning("find_skill: graph upload failed (non-fatal): %s", e)
            return None

    @tool
    def find_skill(query: str) -> str:
        """Traverse the skills knowledge graph to plan how to answer the task.

        Call this FIRST for ANY task needing domain knowledge, a Genie Space ID,
        a SQL pattern, the metric definition / gotchas, chart-selection guidance,
        the design system, the compose-pptx deck spec, or an analytical "why".
        There are NO skill files to read — the graph IS the knowledge. One call
        returns a PLAN: which Genie space to query (+ its space_id), the verbatim
        SQL pattern, the rules/casts to honor, the metric, the chart or deck
        recipe + which tool to call (compose_infographic / compose_deck /
        run_python_notebook), and the relevant insight.

        Phrase ``query`` as the concrete task, e.g.
        "genie space + sql for districts with high health burden but the fewest facilities, and how to chart it",
        "why does healthcare access vary so much from one district to the next",
        "build an RA-branded PowerPoint deck on India's medical deserts". Re-call it
        whenever the task shifts to a new sub-topic.

        ALSO call this when the user says "the data" / "a deep dive" / "explore"
        WITHOUT naming a dataset: the graph knows the full data inventory (the
        domains, Genie spaces, tables and the questions they answer) — query it
        like ``"what datasets, tables and questions does this workspace cover"``,
        then PROPOSE a concrete focus instead of asking the user what data exists.

        Args:
            query: The task or question to plan for.

        Returns:
            A markdown PLAN (routed Genie space, verbatim SQL, gotchas, metric,
            chart/deck recipe + tool, the why) + a traversal-graph link when
            available. Everything needed to act — no file reads.
        """
        if not query or not query.strip():
            return "find_skill needs a non-empty query describing the task."
        try:
            from brain.kg_retrieve import kg_search, format_plan
            db = _get_driver()
            res = kg_search(db, query.strip(), result_k=result_k, embed_fn=_embed)
        except Exception as e:
            logger.warning("find_skill failed: %s", e, exc_info=True)
            return (f"find_skill error: {type(e).__name__}: {e}. The skills "
                    "knowledge graph is unavailable this turn — proceed with your "
                    "best judgement and state any assumption.")
        plan = format_plan(res)
        graph_url = _maybe_upload_graph(res, query.strip())
        if graph_url:
            plan += f"\n\n— Traversal graph view: {graph_url}"
        return plan

    return find_skill


# --- Per-query traversal-graph HTML (self-contained, D3 v7, kind-coloured) ---
_KIND_COLORS = {
    "Question": "#f778ba", "GenieSpace": "#d29922", "SqlPattern": "#58a6ff",
    "Metric": "#3fb950", "Rule": "#f85149", "Table": "#a371f7", "Column": "#6e7681",
    "ChartRecipe": "#56d364", "ChartType": "#2ea043", "DesignRule": "#db61a2",
    "SlideType": "#e3b341", "DeckGuide": "#bb8009", "Tool": "#ff7b72",
    "Finding": "#ffa657", "Country": "#79c0ff", "Domain": "#a5d6ff",
    "Asset": "#484f58", "Concept": "#6e7681",
}


def _subgraph_html(res, query: str) -> str:
    nodes = [{"id": n.id, "label": n.name[:40], "kind": n.kind,
              "score": round(float(n.score), 3), "seed": bool(n.is_seed),
              "snippet": (n.content or "")[:220]} for n in res.nodes]
    links = [{"source": e["a"], "target": e["b"], "kind": e["t"]} for e in res.edges]
    data = {"query": query, "nodes": nodes, "links": links,
            "timings": res.timings_ms, "round_trips": res.db_round_trips}
    payload = json.dumps(data).replace("</", "<\\/")
    return (_GRAPH_HTML_TEMPLATE
            .replace("__GRAPH_DATA__", payload)
            .replace("__KIND_COLORS__", json.dumps(_KIND_COLORS)))


_GRAPH_HTML_TEMPLATE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>find_skill — knowledge-graph traversal</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<style>
  :root{--bg:#0d1117;--panel:#161b22;--line:#30363d;--ink:#e6edf3;--muted:#8b949e}
  *{box-sizing:border-box} html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);font:13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
  #wrap{display:grid;grid-template-columns:1fr 340px;height:100vh}
  svg{width:100%;height:100%;display:block} .panel{background:var(--panel);border-left:1px solid var(--line);padding:16px;overflow:auto}
  .panel h1{font-size:14px;margin:0 0 2px} .q{color:#f778ba;font-weight:600;margin-bottom:8px}
  .legend{display:flex;flex-wrap:wrap;gap:6px 12px;margin:8px 0;font-size:11px;color:var(--muted)}
  .legend span{display:inline-flex;align-items:center;gap:5px} .dot{width:9px;height:9px;border-radius:50%}
  .hit{border-top:1px solid var(--line);padding:7px 0;font-size:12px}
  .hit .k{font-size:10px;text-transform:uppercase;letter-spacing:.04em}
  text{fill:var(--ink);font-size:10px;pointer-events:none}
  .rel{fill:var(--muted);font-size:8.5px}
  .tip{position:fixed;background:#000d;border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:11px;max-width:280px;pointer-events:none;opacity:0}
  #fit{position:fixed;left:12px;top:12px;z-index:5;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:5px 10px;font-size:12px;cursor:pointer}
  #fit:hover{border-color:#8b949e}
  .hint{position:fixed;left:12px;bottom:10px;color:var(--muted);font-size:11px;pointer-events:none}
</style></head><body><div id="wrap">
<button id="fit" title="Fit graph to view">⌖ Fit</button>
<div class="hint">scroll = zoom · drag background = pan · drag node = pin</div>
<svg id="g"></svg>
<div class="panel">
  <h1>Knowledge-graph traversal</h1><div class="q" id="qt"></div>
  <div class="legend" id="legend"></div>
  <div id="meta" class="hit" style="border:0;color:var(--muted)"></div><div id="hits"></div>
</div></div><div class="tip" id="tip"></div>
<script>
const DATA = __GRAPH_DATA__, COLORS = __KIND_COLORS__;
const color = k => COLORS[k] || '#8b949e';
document.getElementById('qt').textContent = DATA.query;
document.getElementById('meta').textContent =
  DATA.nodes.length+' nodes · '+DATA.links.length+' relations · '+DATA.round_trips+' round-trips · '+(DATA.timings.total||'?')+'ms';
const kinds = [...new Set(DATA.nodes.map(n=>n.kind))];
document.getElementById('legend').innerHTML = kinds.map(k=>
  '<span><i class="dot" style="background:'+color(k)+'"></i>'+k+'</span>').join('');
const hits = document.getElementById('hits');
DATA.nodes.filter(n=>n.seed).sort((a,b)=>b.score-a.score).forEach((n,i)=>{
  const d=document.createElement('div'); d.className='hit';
  d.innerHTML='<span class="k" style="color:'+color(n.kind)+'">'+n.kind+'</span> · <b>'+n.label+'</b> · '+n.score;
  hits.appendChild(d);
});
const svg=d3.select('#g'), W=svg.node().clientWidth, H=svg.node().clientHeight;
// Zoomable/pannable canvas: everything draws inside gRoot; d3.zoom on the svg
// (wheel = zoom, drag background = pan, double-click = zoom in). Nodes are also
// clamped to a bounded box during the simulation so they can never fly off.
const gRoot=svg.append('g');
const zoom=d3.zoom().scaleExtent([0.2,5]).on('zoom',e=>gRoot.attr('transform',e.transform));
svg.call(zoom);
const BX=Math.max(W*1.4,900), BY=Math.max(H*1.4,700);          // simulation bounds
const link=gRoot.append('g').attr('stroke','#30363d').attr('stroke-opacity',.65)
  .selectAll('line').data(DATA.links).join('line').attr('stroke-width',1);
const lbl=gRoot.append('g').selectAll('text').data(DATA.links).join('text')
  .attr('class','rel').text(d=>d.kind);
const node=gRoot.append('g').selectAll('g').data(DATA.nodes).join('g').call(drag())
  .style('cursor','grab');
node.append('circle').attr('r',d=>d.seed?7+8*(d.score||0):5)
  .attr('fill',d=>color(d.kind)).attr('stroke','#0d1117').attr('stroke-width',1.5);
node.append('text').attr('x',10).attr('dy','.35em').text(d=>d.label);
const tip=d3.select('#tip');
node.on('mousemove',(e,d)=>tip.style('opacity',1).style('left',(e.clientX+12)+'px').style('top',(e.clientY+12)+'px')
   .html('<b>'+d.kind+': '+d.label+'</b><br>'+(d.snippet||'')+'…'))
   .on('mouseout',()=>tip.style('opacity',0));
const sim=d3.forceSimulation(DATA.nodes)
  .force('link',d3.forceLink(DATA.links).id(d=>d.id).distance(95))
  .force('charge',d3.forceManyBody().strength(-300))
  .force('center',d3.forceCenter(W/2,H/2))
  .force('x',d3.forceX(W/2).strength(0.05)).force('y',d3.forceY(H/2).strength(0.06))
  .force('collide',d3.forceCollide(26));
const clampX=x=>Math.max(W/2-BX/2,Math.min(W/2+BX/2,x)), clampY=y=>Math.max(H/2-BY/2,Math.min(H/2+BY/2,y));
sim.on('tick',()=>{ DATA.nodes.forEach(d=>{d.x=clampX(d.x);d.y=clampY(d.y);});
  link.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y).attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
  lbl.attr('x',d=>(d.source.x+d.target.x)/2).attr('y',d=>(d.source.y+d.target.y)/2);
  node.attr('transform',d=>`translate(${d.x},${d.y})`); });
// Fit the settled layout into the viewport (and on demand via the ⌖ button).
function fit(){ if(!DATA.nodes.length) return;
  const xs=DATA.nodes.map(d=>d.x), ys=DATA.nodes.map(d=>d.y);
  const x0=Math.min(...xs)-40,x1=Math.max(...xs)+150,y0=Math.min(...ys)-30,y1=Math.max(...ys)+30;
  const k=Math.min(2,0.92/Math.max((x1-x0)/W,(y1-y0)/H));
  svg.transition().duration(450).call(zoom.transform,
    d3.zoomIdentity.translate(W/2-k*(x0+x1)/2,H/2-k*(y0+y1)/2).scale(k)); }
sim.on('end',fit); setTimeout(fit,1800);
d3.select('#fit').on('click',fit);
function drag(){ return d3.drag()
  .on('start',(e,d)=>{if(!e.active)sim.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y;})
  .on('drag',(e,d)=>{d.fx=e.x;d.fy=e.y;})
  .on('end',(e,d)=>{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}); }
</script></body></html>"""
