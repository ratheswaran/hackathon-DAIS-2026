"""compose_story — freehand D3 data-story escape hatch (bespoke scrollytelling).

For the deterministic, native chart library + multi-panel report stories use
``compose_infographic``. Reach for ``compose_story`` ONLY when the user wants a
*bespoke* scroll-driven essay that the scene archetypes can't express — e.g. the
flagship 3-chapter sticky-scroll narrative where the chart in a sticky panel
*swaps* as the reader scrolls past prose steps.

Design — SAFE data injection, NO server-side code execution:

    The agent writes (or copies from the compose-pptx-style flagship recipe) a
    fully self-contained HTML document that carries exactly ONE quoted token,
    ``"__DATA__"``, inside ``const DATA = "__DATA__";`` (the validated build_*.py
    idiom). It separately computes a JSON-serializable ``data`` dict — using the
    already-sandboxed ``run_python_code`` over stored DataFrames, so every figure
    is grounded and verifiable. This tool does NOT exec the agent's code: it
    validates the template, injects ``json.dumps(data)`` at the token (and the
    shared RA palette at an optional ``"__PALETTE__"`` token), uploads the result
    to UC Volumes, and returns a proxied ``/api/infographics/<id>`` URL.

    That keeps the freehand path's expressive power without a code-exec surface:
    the only thing that runs is the browser rendering trusted-shape HTML.

Output mirrors compose_infographic (same volume folder + ``/api/infographics``
route) so the frontend artifact dock handles both identically.
"""

from __future__ import annotations

import hashlib
import json
import logging
from io import BytesIO
from typing import Annotated, Any, Callable

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore

from tools.compact_ref import _compact_error

logger = logging.getLogger(__name__)

_VOLUME_ROOT = "/Volumes/workspace/ai_ops/agent_scratch/infographics"
_DATA_TOKEN = '"__DATA__"'
_PALETTE_TOKEN = '"__PALETTE__"'
_MAX_TEMPLATE_BYTES = 2_000_000  # 2 MB guard

# Mirror of skills/design_system/tokens.css — injected at the optional
# "__PALETTE__" token so freehand templates inherit the brand without hardcoding.
_PALETTE_JS = {
    "paper": "#FAF6EE", "oat": "#F5EFE3", "ink": "#1F1B16", "slate": "#3A3A40",
    "mute": "#9CA0A3", "grey": "#C7C2B6", "hair": "rgba(58,58,64,.12)",
    "signal": "#254BB2", "signalDim": "#5B79C9", "amber": "#DF9B44",
    "cyan": "#2695AC", "magenta": "#913F82", "alarm": "#A6402E",
    "inkBg": "#14110D", "onInk": "#F5EFE3", "onInkMute": "#B8B2A6", "onInkAccent": "#DF9B44",
    "serif": '"Source Serif 4",Georgia,serif',
    "sans": '"Manrope",system-ui,sans-serif',
    "mono": '"JetBrains Mono",ui-monospace,monospace',
}


def _story_id(title: str, template_html: str) -> str:
    # Same `infographic_<12hex>` shape as compose_infographic so the existing
    # /api/infographics/:id route + frontend dock serve both identically
    # (route regex: ^infographic_[a-f0-9]{8,16}$).
    h = hashlib.sha256(f"story|{title}|{template_html[:4000]}".encode("utf-8")).hexdigest()[:12]
    return f"infographic_{h}"


def _validate(title: str, template_html: str, data: Any) -> tuple[bool, str]:
    if not title or not title.strip():
        return False, "title is required"
    if not isinstance(template_html, str) or not template_html.strip():
        return False, "template_html is required (a self-contained HTML document)"
    if len(template_html.encode("utf-8")) > _MAX_TEMPLATE_BYTES:
        return False, f"template_html exceeds {_MAX_TEMPLATE_BYTES} bytes"
    low = template_html.lstrip().lower()
    if not (low.startswith("<!doctype") or low.startswith("<html")):
        return False, "template_html must be a full HTML document (start with <!DOCTYPE html> or <html>)"
    if _DATA_TOKEN not in template_html:
        return False, 'template_html must contain the literal token "__DATA__" (inside const DATA = "__DATA__";) for data injection'
    if data is None:
        return False, "data is required (a JSON-serializable object the template reads as DATA)"
    try:
        json.dumps(data)
    except (TypeError, ValueError) as e:
        return False, f"data is not JSON-serializable: {e}"
    return True, ""


def build_compose_story_tool(*, workspace_client: Any, variable_store_cls: Callable = None, app_url: str = ""):
    """Factory mirroring compose_infographic's signature (variable_store_cls unused;
    kept for factory parity)."""
    _ = variable_store_cls

    @tool
    def compose_story(
        title: Annotated[str, "Short, sober story title (no emoji). Time scope in the title when relevant."],
        template_html: Annotated[
            str,
            "A COMPLETE self-contained HTML document (starts <!DOCTYPE html>) containing the "
            "literal token \"__DATA__\" exactly as `const DATA = \"__DATA__\";` — the tool replaces "
            "it with your `data` as JSON. Optionally include `const P = \"__PALETTE__\";` to get "
            "the shared RA palette injected. MANDATORY: first call "
            "find_skill(\"scrollytelling story recipe\") and follow its HARD RULES verbatim — the "
            "sticky chart is a scroll-driven state machine (render(svg,ch,ci,si) re-invoked ONLY "
            "on step change via the lastSi[] RENDER-GUARD), per-scene root groups with scene-swap "
            "cleanup, an OPAQUE sticky panel sized width:100% of its grid column (never a fixed px "
            "width wider than the column), titles anchored at the svg edge, dodged/clamped labels, "
            "explicit font-size on every svg text node. Step 0 paints the complete chart; "
            "transitions use the reduced-motion-guarded T() helper. NO hand-typed figures — every "
            "number comes from `data`.",
        ],
        data: Annotated[
            dict,
            "JSON-serializable dict holding EVERY figure/label the template renders, computed via "
            "run_python_code over stored DataFrames. The template reads it as the global DATA.",
        ],
        store: Annotated[Any, InjectedStore()] = None,
        config: RunnableConfig = None,
    ) -> str:
        """Inject `data` into a bespoke self-contained HTML story template and publish it.

        Use ONLY for bespoke scroll-driven essays the compose_infographic archetypes can't
        express; standard single-chart or multi-panel report stories go to compose_infographic.

        Returns compact JSON {"status":"ok","infographic_id":..,"url":..}. The frontend
        auto-opens the artifact — reference the story by TITLE in prose; never paste the raw
        JSON or the Volumes path.
        """
        try:
            ok, msg = _validate(title, template_html, data)
            if not ok:
                return _compact_error(error_type="bad_spec", message=msg)

            html_str = template_html.replace(_DATA_TOKEN, json.dumps(data, ensure_ascii=False))
            if _PALETTE_TOKEN in html_str:
                html_str = html_str.replace(_PALETTE_TOKEN, json.dumps(_PALETTE_JS, ensure_ascii=False))

            iid = _story_id(title, template_html)
            html_path = f"{_VOLUME_ROOT}/{iid}.html"
            try:
                workspace_client.files.create_directory(_VOLUME_ROOT)
            except Exception:
                pass
            workspace_client.files.upload(html_path, BytesIO(html_str.encode("utf-8")), overwrite=True)

            url = f"{app_url.rstrip('/')}/api/infographics/{iid}" if app_url else f"/api/infographics/{iid}"
            return json.dumps(
                {"status": "ok", "infographic_id": iid, "title": title, "kind": "story", "url": url},
                separators=(",", ":"),
            )
        except Exception as e:
            logger.exception("compose_story failed")
            return _compact_error(error_type="render_error", message=str(e)[:200])

    return compose_story


# ── Local validation entrypoint (no Databricks SDK) ──────────────────────
def _inject_local(template_html: str, data: Any) -> str:
    """Pure injection for pytest / local preview (no upload)."""
    out = template_html.replace(_DATA_TOKEN, json.dumps(data, ensure_ascii=False))
    if _PALETTE_TOKEN in out:
        out = out.replace(_PALETTE_TOKEN, json.dumps(_PALETTE_JS, ensure_ascii=False))
    return out
