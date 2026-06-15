/**
 * GET /api/documents/:id — Proxy binary office documents from Databricks Volumes.
 *
 * The hackathon orchestrator's `compose_document` tool writes pptx/docx/xlsx/csv/pdf
 * payloads to `/Volumes/workspace/ai_ops/agent_scratch/documents/<id>__<slug>.<fmt>`
 * via the Files API and returns compact JSON with `document_id`. This route
 * looks up the matching file in the documents folder and streams it back with
 * `Content-Disposition: attachment` so the browser downloads instead of
 * trying to render. The frontend's artifact dock renders a download card and
 * points its <a download> at this URL.
 *
 * Path shape locked at: `/Volumes/workspace/ai_ops/agent_scratch/documents/<id>__<slug>.<fmt>`
 * (defined in hackathon-orchestrator/tools/compose_document.py — keep in sync).
 *
 * Identifier shape: `document_<format>_<12hex>` — verified against `compose_document`.
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

export const documentsRouter: RouterType = Router();

documentsRouter.use(authMiddleware);

const DOCUMENT_ROOT = '/Volumes/workspace/ai_ops/agent_scratch/documents';

// MIME types for the five supported formats. Anything else falls back to
// application/octet-stream which still downloads cleanly.
const MIME_BY_FORMAT: Record<string, string> = {
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  csv: 'text/csv; charset=utf-8',
  pdf: 'application/pdf',
};

documentsRouter.get(
  '/:id',
  requireAuth,
  async (req: Request, res: Response) => {
    const { id } = req.params;

    // compose_document emits ids like `document_<format>_<12hex>`.
    const idMatch = /^document_([a-z]+)_([a-f0-9]{8,16})$/.exec(id);
    if (!idMatch) {
      return res.status(400).json({ error: 'Invalid document id' });
    }
    const fmt = idMatch[1];

    try {
      const hostUrl = getHostUrl();
      const token = await getDatabricksToken();

      // The on-volume filename has a slug suffix the orchestrator chose at
      // upload time, so we don't know the exact path from the id alone. List
      // the documents directory and pick the entry whose name starts with
      // `<id>__`. Mirrors how compose_document writes:
      //   `${DOCUMENT_ROOT}/${doc_id}__${slug}.${fmt}`
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
          `[/api/documents] directory listing failed: ${listResp.status} ${listResp.statusText} body=${body}`,
        );
        if (listResp.status === 404) {
          return res.status(404).json({ error: 'Documents folder not found' });
        }
        if (listResp.status === 403) {
          return res
            .status(403)
            .json({ error: 'App SP lacks READ_VOLUME on documents path' });
        }
        return res
          .status(502)
          .json({ error: 'Failed to list documents folder' });
      }

      const listJson = (await listResp.json()) as {
        contents?: Array<{ name?: string; path?: string }>;
      };
      const entry = (listJson.contents ?? []).find((e) => {
        const name = e.name ?? '';
        return name.startsWith(`${id}__`) && name.endsWith(`.${fmt}`);
      });

      if (!entry || !entry.path) {
        return res.status(404).json({ error: 'Document not found' });
      }

      const filePath = entry.path;
      const upstreamUrl = `${hostUrl}/api/2.0/fs/files${filePath}`;

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
          `[/api/documents] Volumes fetch failed: ${upstream.status} ${upstream.statusText} ` +
            `for ${filePath} body=${body}`,
        );
        return res
          .status(502)
          .json({ error: 'Failed to fetch document from storage' });
      }

      // Pull a human-friendly filename out of the entry's basename — the
      // orchestrator slug is already filesystem-safe (see compose_document
      // `_slug()`), so we just trim off the `<id>__` prefix.
      const basename = (entry.name ?? `${id}.${fmt}`).replace(
        new RegExp(`^${id}__`),
        '',
      );
      const mime = MIME_BY_FORMAT[fmt] ?? 'application/octet-stream';

      res.setHeader('Content-Type', mime);
      res.setHeader(
        'Content-Disposition',
        `attachment; filename="${basename.replace(/"/g, '\\"')}"`,
      );
      res.setHeader('Cache-Control', 'private, max-age=300');
      res.setHeader('X-Content-Type-Options', 'nosniff');

      const buf = Buffer.from(await upstream.arrayBuffer());
      res.send(buf);
    } catch (error) {
      console.error('[/api/documents] Error:', error);
      res.status(500).json({ error: 'Internal server error' });
    }
  },
);
