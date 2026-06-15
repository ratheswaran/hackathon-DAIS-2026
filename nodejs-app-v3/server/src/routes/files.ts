/**
 * /api/files — user file uploads for the chat composer's "+" button.
 *
 * POST /api/files/upload?filename=<name>   (raw body = the file bytes)
 *   → stores the file in the agent-scratch Volume under uploads/, where the
 *     agent's virtual filesystem can read it at `/uploads/<stored-name>`
 *     (DatabricksVolumesBackend maps "/" → the agent_scratch Volume root).
 *   → responds { url, pathname, contentType } — the shape the composer's
 *     attachment flow expects — plus agentPath for the chat route to inject.
 *
 * GET /api/files/:name → proxies the stored file back (composer image
 *     previews + downloads).
 *
 * The client sends RAW bytes (no multipart) so no parser dependency is needed.
 */

import { randomBytes } from 'node:crypto';
import {
  Router,
  raw,
  type Request,
  type Response,
  type Router as RouterType,
} from 'express';
import { authMiddleware, requireAuth } from '../middleware/auth';
import { getHostUrl } from '@chat-template/utils';
import { getDatabricksToken } from '@chat-template/auth';

export const filesRouter: RouterType = Router();

filesRouter.use(authMiddleware);

// Same Volume the agent's virtual filesystem is rooted at.
const UPLOADS_ROOT = '/Volumes/workspace/ai_ops/agent_scratch/uploads';
const MAX_BYTES = 25 * 1024 * 1024; // 25 MB

const STORED_NAME = /^[a-f0-9]{8}__[A-Za-z0-9._-]{1,128}$/;

function sanitizeFilename(name: string): string {
  const base = name.split(/[\\/]/).pop() || 'file';
  return base.replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 128) || 'file';
}

filesRouter.post(
  '/upload',
  requireAuth,
  raw({ type: () => true, limit: MAX_BYTES }),
  async (req: Request, res: Response) => {
    const rawName = String(req.query.filename || 'file');
    const safe = sanitizeFilename(rawName);
    const stored = `${randomBytes(4).toString('hex')}__${safe}`;
    const body = req.body as Buffer;

    if (!body || !Buffer.isBuffer(body) || body.length === 0) {
      return res.status(400).json({ error: 'Empty upload body' });
    }

    try {
      const hostUrl = getHostUrl();
      const token = await getDatabricksToken();
      const upstream = await fetch(
        `${hostUrl}/api/2.0/fs/files${UPLOADS_ROOT}/${stored}?overwrite=true`,
        {
          method: 'PUT',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/octet-stream',
          },
          body: new Uint8Array(body),
        },
      );
      if (!upstream.ok) {
        const detail = (await upstream.text().catch(() => '')).slice(0, 300);
        console.error(
          `[/api/files/upload] Volumes PUT failed: ${upstream.status} ${detail}`,
        );
        return res
          .status(502)
          .json({ error: 'Failed to store the file. Please try again.' });
      }
      return res.json({
        url: `/api/files/${stored}`,
        pathname: safe,
        // The client always POSTs octet-stream (so the global JSON body parser
        // can't consume .json uploads) and passes the real type as ?type=.
        contentType: String(req.query.type || 'application/octet-stream'),
        agentPath: `/uploads/${stored}`,
      });
    } catch (e) {
      console.error('[/api/files/upload] error', e);
      return res.status(500).json({ error: 'Upload failed' });
    }
  },
);

filesRouter.get('/:name', requireAuth, async (req: Request, res: Response) => {
  const name = String(req.params.name);
  if (!STORED_NAME.test(name)) {
    return res.status(400).json({ error: 'Invalid file name' });
  }
  try {
    const hostUrl = getHostUrl();
    const token = await getDatabricksToken();
    const upstream = await fetch(
      `${hostUrl}/api/2.0/fs/files${UPLOADS_ROOT}/${name}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (!upstream.ok) {
      return res
        .status(upstream.status === 404 ? 404 : 502)
        .json({ error: 'File not found' });
    }
    const buf = Buffer.from(await upstream.arrayBuffer());
    // Infer a content type from the extension for image previews.
    const ext = (name.split('.').pop() || '').toLowerCase();
    const types: Record<string, string> = {
      png: 'image/png',
      jpg: 'image/jpeg',
      jpeg: 'image/jpeg',
      gif: 'image/gif',
      webp: 'image/webp',
      svg: 'image/svg+xml',
      pdf: 'application/pdf',
      csv: 'text/csv; charset=utf-8',
      txt: 'text/plain; charset=utf-8',
      json: 'application/json',
      md: 'text/markdown; charset=utf-8',
    };
    res.setHeader('Content-Type', types[ext] || 'application/octet-stream');
    res.setHeader('Cache-Control', 'private, max-age=3600');
    return res.send(buf);
  } catch (e) {
    console.error('[/api/files] proxy error', e);
    return res.status(500).json({ error: 'Failed to fetch file' });
  }
});
