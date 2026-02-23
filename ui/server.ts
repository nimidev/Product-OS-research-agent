import express from "express";
import { createServer as createViteServer } from "vite";
import Database from "better-sqlite3";
import path from "path";

const db = new Database("product_os.db");

// Initialize DB
db.exec(`
  CREATE TABLE IF NOT EXISTS config (
    id TEXT PRIMARY KEY,
    data TEXT
  );
  CREATE TABLE IF NOT EXISTS context_items (
    id TEXT PRIMARY KEY,
    type TEXT,
    source TEXT,
    data TEXT
  );
`);

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json());

  // API Routes
  app.get("/api/config", (req, res) => {
    const row = db.prepare("SELECT data FROM config WHERE id = 'current'").get() as { data: string } | undefined;
    res.json(row ? JSON.parse(row.data) : {});
  });

  app.post("/api/config", (req, res) => {
    const data = JSON.stringify(req.body);
    db.prepare("INSERT OR REPLACE INTO config (id, data) VALUES ('current', ?)").run(data);
    res.json({ status: "ok" });
  });

  app.get("/api/context-items", (req, res) => {
    const rows = db.prepare("SELECT * FROM context_items").all() as any[];
    res.json(rows.map(r => ({ ...JSON.parse(r.data), id: r.id, source_type: r.source })));
  });

  app.post("/api/seed", (req, res) => {
    const { items } = req.body;
    const insert = db.prepare("INSERT OR REPLACE INTO context_items (id, type, source, data) VALUES (?, ?, ?, ?)");
    const transaction = db.transaction((items) => {
      for (const item of items) {
        insert.run(item.id, item.type || 'unknown', item.source_type, JSON.stringify(item));
      }
    });
    transaction(items);
    res.json({ status: "ok" });
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.join(__dirname, "dist")));
    app.get("*", (req, res) => {
      res.sendFile(path.join(__dirname, "dist", "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
