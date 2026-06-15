/**
 * GET /api/infographics/:id — Proxy D3 infographic HTML from Databricks Volumes.
 *
 * The hackathon orchestrator's `compose_infographic` tool writes self-contained
 * D3 v7 HTML to `/Volumes/workspace/ai_ops/agent_scratch/infographics/{id}.html`
 * and returns compact JSON containing `infographic_id`. This route fetches the
 * HTML via the Databricks Files API and streams it back. The frontend's
 * artifact dock iframes this URL.
 *
 * Path shape locked at: `/Volumes/workspace/ai_ops/agent_scratch/infographics/{id}.html`
 * (defined in hackathon-orchestrator/tools/compose_infographic.py — keep in sync).
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

export const infographicsRouter: RouterType = Router();

infographicsRouter.use(authMiddleware);

// Locked location for hackathon infographics. Changing this requires updating
// `scratch_root` in compose_infographic.py and redeploying.
const INFOGRAPHIC_ROOT =
  '/Volumes/workspace/ai_ops/agent_scratch/infographics';

infographicsRouter.get(
  '/:id',
  requireAuth,
  async (req: Request, res: Response) => {
    const { id } = req.params;

    // compose_infographic emits ids like `infographic_<12hex>`.
    if (!/^infographic_[a-f0-9]{8,16}$/.test(id)) {
      return res.status(400).json({ error: 'Invalid infographic id' });
    }

    const volumesPath = `${INFOGRAPHIC_ROOT}/${id}.html`;

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
          `[/api/infographics] Volumes fetch failed: ${upstream.status} ${upstream.statusText} ` +
            `for ${volumesPath} body=${body}`,
        );
        if (upstream.status === 404) {
          return res.status(404).json({ error: 'Infographic not found' });
        }
        if (upstream.status === 403) {
          return res
            .status(403)
            .json({ error: 'App SP lacks READ_VOLUME on infographics path' });
        }
        return res
          .status(502)
          .json({ error: 'Failed to fetch infographic from storage' });
      }

      const html = await upstream.text();
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.setHeader('Cache-Control', 'public, max-age=3600');
      res.setHeader('X-Content-Type-Options', 'nosniff');
      res.send(html);
    } catch (error) {
      console.error('[/api/infographics] Error:', error);
      res.status(500).json({ error: 'Internal server error' });
    }
  },
);
