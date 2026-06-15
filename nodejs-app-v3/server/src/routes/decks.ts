/**
 * GET /api/decks/:id[.ext] — Proxy deck artifacts from Databricks Volumes.
 *
 * The hackathon orchestrator's `compose_deck` tool writes three files for
 * each deck composition (hackathon Free-Edition `workspace` catalog):
 *
 *   /Volumes/workspace/ai_ops/agent_scratch/documents/<id>__<slug>.html
 *   /Volumes/workspace/ai_ops/agent_scratch/documents/<id>__<slug>.pptx
 *   /Volumes/workspace/ai_ops/agent_scratch/documents/<id>__<slug>.json
 *
 * where `<id>` matches `deck_[a-f0-9]{12}`. This route serves whichever
 * extension is requested (the RA compose_deck emits no PDF — export from
 * PowerPoint — so `.pdf` requests simply 404):
 *
 *   GET /api/decks/<id>         → text/html (preview in browser)
 *   GET /api/decks/<id>.pptx    → application/vnd...presentation (download)
 *   GET /api/decks/<id>.pdf     → application/pdf (download, if present)
 *
 * Identical proxying pattern to documents.ts — list the documents folder,
 * pick the entry whose name starts with `<id>__` and ends with the right
 * extension, stream it back. Differences from documents.ts:
 *
 *   - extension dispatch is per-URL, not encoded in the id (compose_deck
 *     produces three files per call; we don't want three separate ids)
 *   - HTML is served inline (Content-Disposition omitted) so it renders
 *     in-browser; pptx/pdf are sent as download attachments
 *   - id pattern is `deck_<hex>` not `document_<format>_<hex>`
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

export const decksRouter: RouterType = Router();

decksRouter.use(authMiddleware);

const DOCUMENT_ROOT = '/Volumes/workspace/ai_ops/agent_scratch/documents';

// MIME types + whether the browser should render inline (HTML) vs
// download (binary office formats).
const MIME_BY_EXT: Record<string, { mime: string; inline: boolean }> = {
  html: { mime: 'text/html; charset=utf-8', inline: true },
  pptx: {
    mime: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    inline: false,
  },
  pdf: { mime: 'application/pdf', inline: false },
};

// Matches `<id>` or `<id>.<ext>` at the end of the path. The id is always
// `deck_<12hex>`; the ext (when present) is one of html/pptx/pdf.
const ID_PATTERN = /^(deck_[a-f0-9]{8,16})(?:\.(html|pptx|pdf))?$/;

decksRouter.get(
  '/:idAndExt',
  requireAuth,
  async (req: Request, res: Response) => {
    const { idAndExt } = req.params;

    const m = ID_PATTERN.exec(idAndExt);
    if (!m) {
      return res.status(400).json({ error: 'Invalid deck id or extension' });
    }
    const id = m[1];
    const ext = (m[2] ?? 'html') as 'html' | 'pptx' | 'pdf';

    try {
      const hostUrl = getHostUrl();
      const token = await getDatabricksToken();

      // List documents/ and pick the entry whose name starts with `<id>__`
      // and ends with the requested extension. The slug suffix is chosen
      // at upload time by compose_deck — we can't reconstruct the path
      // from id+ext alone.
      const listUrl = `${hostUrl}/api/2.0/fs/directories${DOCUMENT_ROOT}`;
      const listResp = await fetch(listUrl, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!listResp.ok) {
        let body = '';
        try {
          body = (await listResp.text()).slice(0, 400);
        } catch {
          /* ignore */
        }
        console.error(
          `[/api/decks] directory listing failed: ${listResp.status} ${listResp.statusText} body=${body}`,
        );
        if (listResp.status === 404) {
          return res.status(404).json({ error: 'Documents folder not found' });
        }
        if (listResp.status === 403) {
          return res
            .status(403)
            .json({ error: 'App SP lacks READ_VOLUME on documents path' });
        }
        return res.status(502).json({ error: 'Failed to list deck folder' });
      }

      const listJson = (await listResp.json()) as {
        contents?: Array<{ name?: string; path?: string }>;
      };
      const entry = (listJson.contents ?? []).find((e) => {
        const name = e.name ?? '';
        return name.startsWith(`${id}__`) && name.endsWith(`.${ext}`);
      });

      if (!entry || !entry.path) {
        return res
          .status(404)
          .json({ error: `Deck not found: ${id}.${ext}` });
      }

      const filePath = entry.path;
      const upstream = await fetch(`${hostUrl}/api/2.0/fs/files${filePath}`, {
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
          `[/api/decks] Volumes fetch failed: ${upstream.status} ${upstream.statusText} ` +
            `for ${filePath} body=${body}`,
        );
        return res
          .status(502)
          .json({ error: 'Failed to fetch deck from storage' });
      }

      // Drop the `<id>__` prefix so the user gets a clean filename.
      const basename = (entry.name ?? `${id}.${ext}`).replace(
        new RegExp(`^${id}__`),
        '',
      );
      const { mime, inline } = MIME_BY_EXT[ext];

      res.setHeader('Content-Type', mime);
      res.setHeader(
        'Content-Disposition',
        inline
          ? `inline; filename="${basename.replace(/"/g, '\\"')}"`
          : `attachment; filename="${basename.replace(/"/g, '\\"')}"`,
      );
      res.setHeader('Cache-Control', 'private, max-age=300');
      res.setHeader('X-Content-Type-Options', 'nosniff');

      const buf = Buffer.from(await upstream.arrayBuffer());
      res.send(buf);
    } catch (error) {
      console.error('[/api/decks] Error:', error);
      res.status(500).json({ error: 'Internal server error' });
    }
  },
);
