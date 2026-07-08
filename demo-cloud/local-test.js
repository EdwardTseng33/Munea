// 本機測試小伺服器（不會被部署，.vercelignore 有排除）
// 用法：node local-test.js  → http://localhost:8299
// 鑰匙：自動讀 ../engine/.env.local
const http = require("http");
const fs = require("fs");
const path = require("path");
const tokenHandler = require("./api/token.js");

// 讀鑰匙進環境變數（模擬 Vercel 環境變數）
const envFile = path.join(__dirname, "..", "engine", ".env.local");
for (const line of fs.readFileSync(envFile, "utf8").split(/\r?\n/)) {
  const m = line.match(/^([A-Z_]+)=(.*)$/);
  if (m && !process.env[m[1]]) process.env[m[1]] = m[2].trim();
}

const MIME = { ".html": "text/html; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".js": "text/javascript" };

http.createServer(async (req, res) => {
  if (req.url.startsWith("/api/token")) return tokenHandler(req, res);
  let p = req.url.split("?")[0];
  if (p === "/") p = "/index.html";
  const fp = path.normalize(path.join(__dirname, p));
  if (!fp.startsWith(__dirname) || !fs.existsSync(fp) || !fs.statSync(fp).isFile()) {
    res.statusCode = 404; return res.end("not found");
  }
  res.setHeader("Content-Type", MIME[path.extname(fp)] || "application/octet-stream");
  res.end(fs.readFileSync(fp));
}).listen(8299, () => console.log("local demo-cloud on http://localhost:8299"));
