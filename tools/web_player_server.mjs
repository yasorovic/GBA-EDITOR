/** Serveur local du lecteur web (web_player/) ou d'un ZIP web extrait.
 *
 * Usage : node tools/web_player_server.mjs [dossier du ZIP extrait]
 * Puis ouvrir http://localhost:8000 dans un navigateur récent.
 */

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, isAbsolute, relative, resolve, sep } from "node:path";

const root = process.argv[2] ? resolve(process.argv[2]) : resolve(import.meta.dirname, "..", "web_player");
const port = Number(process.env.BACKSTAGE_WEB_PORT ?? 8000);
const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
  ".wasm": "application/wasm",
};

const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, "http://localhost").pathname;
    const filePath = resolve(root, pathname === "/" ? "index.html" : decodeURIComponent(pathname).slice(1));
    const withinRoot = relative(root, filePath);
    if (isAbsolute(withinRoot) || withinRoot === ".." || withinRoot.startsWith(`..${sep}`)) {
      response.writeHead(403).end("Forbidden");
      return;
    }
    const body = await readFile(filePath);
    response.writeHead(200, {
      "Content-Type": contentTypes[extname(filePath)] ?? "application/octet-stream",
    });
    response.end(body);
  } catch {
    response.writeHead(404).end("Not found");
  }
}).listen(port, "127.0.0.1", () => {
  console.log(`Prototype HTML : http://localhost:${server.address().port}`);
});
