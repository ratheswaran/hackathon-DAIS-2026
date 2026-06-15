/**
 * GET /api/skill_graph/:file — Proxy find_skill traversal-graph HTML from Volumes.
 *
 * The neo4j orchestrator's `find_skill` tool uploads a per-query D3 subgraph to
 * `/Volumes/workspace/ai_ops/agent_scratch/skill_graphs/skillgraph_{gid}.html`
 * and appends `{APP_URL}/api/skill_graph/{gid}.html` to its plan. This route
 * fetches the HTML via the Databricks Files API and streams it back. The
 * frontend's artifact dock iframes this URL; `explorer.html` is the
 * full-graph knowledge-graph explorer linked from the chat header.
 *
 * Path shape locked at: `.../agent_scratch/skill_graphs/skillgraph_{gid}.html`
 * (defined in hackathon-orchestrator-neo4j/tools/find_skill.py — keep in sync).
 */

import {
  Router,
  type Request,
  type Response,
  type Router as RouterType,
} from 'express';
import { authMiddleware, requireAuth } from '../middleware/auth';
import { getHostUrl } from '@chat-template/utils';
import { getDatabricksToken } from '@chat-template/auth';

export const skillGraphRouter: RouterType = Router();

skillGraphRouter.use(authMiddleware);

// Locked location for find_skill traversal graphs. Changing this requires
// updating `volume_dir` in find_skill.py and redeploying the orchestrator.
const SKILL_GRAPH_ROOT = '/Volumes/workspace/ai_ops/agent_scratch/skill_graphs';

skillGraphRouter.get(
  '/:file',
  requireAuth,
  async (req: Request, res: Response) => {
    const { file } = req.params;

    // find_skill links use the bare gid (`{gid}.html`); the Volume file is
    // `skillgraph_{gid}.html`. `explorer.html` is the full-graph explorer.
    let volumesPath: string;
    const gidMatch = /^(?:skillgraph_)?([a-f0-9]{8,16})\.html$/.exec(file);
    if (gidMatch) {
      volumesPath = `${SKILL_GRAPH_ROOT}/skillgraph_${gidMatch[1]}.html`;
    } else if (file === 'explorer.html') {
      volumesPath = `${SKILL_GRAPH_ROOT}/explorer.html`;
    } else {
      return res.status(400).json({ error: 'Invalid skill graph id' });
    }

    try {
      const hostUrl = getHostUrl();
      const token = await getDatabricksToken();

      const upstreamUrl = `${hostUrl}/api/2.0/fs/files${volumesPath}`;

      const upstream = await fetch(upstreamUrl, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!upstream.ok) {
        let body = '';
        try {
          body = (await upstream.text()).slice(0, 400);
        } catch {
          /* ignore */
        }
        console.error(
          `[/api/skill_graph] Volumes fetch failed: ${upstream.status} ${upstream.statusText} ` +
            `for ${volumesPath} body=${body}`,
        );
        if (upstream.status === 404) {
          return res.status(404).json({ error: 'Skill graph not found' });
        }
        if (upstream.status === 403) {
          return res
            .status(403)
            .json({ error: 'App SP lacks READ_VOLUME on skill_graphs path' });
        }
        return res
          .status(502)
          .json({ error: 'Failed to fetch skill graph from storage' });
      }

      const html = await upstream.text();
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.setHeader('Cache-Control', 'public, max-age=3600');
      res.setHeader('X-Content-Type-Options', 'nosniff');
      res.send(html);
    } catch (error) {
      console.error('[/api/skill_graph] Error:', error);
      res.status(500).json({ error: 'Internal server error' });
    }
  },
);
