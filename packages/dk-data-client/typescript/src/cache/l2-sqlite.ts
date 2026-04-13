/**
 * SQLite-backed L2 cache for dev and single-process consumers.
 *
 * Uses `better-sqlite3` as an optional peer dependency (synchronous under
 * the hood, wrapped in async for interface parity).
 */

import type { L2Backend } from "./index.js";

interface SqliteDatabaseLike {
  prepare(sql: string): {
    run(...args: unknown[]): unknown;
    get(...args: unknown[]): unknown;
  };
  exec(sql: string): void;
  close(): void;
}

type SqliteCtor = new (
  path: string,
  opts?: { fileMustExist?: boolean },
) => SqliteDatabaseLike;

interface CacheRow {
  value: string;
  expires_at: number;
}

export class SqliteL2Cache implements L2Backend {
  private readonly db: SqliteDatabaseLike;

  constructor(dbPath: string) {
    let Database: SqliteCtor;
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      Database = require("better-sqlite3") as SqliteCtor;
    } catch {
      throw new Error(
        "SQLite cache backend requires the 'better-sqlite3' peer dependency. " +
          "Install it with `pnpm add better-sqlite3`.",
      );
    }
    this.db = new Database(dbPath);
    this.db.exec("PRAGMA journal_mode = WAL");
    this.db.exec(
      "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT, expires_at INTEGER)",
    );
  }

  async get(key: string): Promise<unknown> {
    const row = this.db.prepare("SELECT value, expires_at FROM cache WHERE key = ?").get(key) as
      | CacheRow
      | undefined;
    if (!row) return null;
    if (row.expires_at < Math.floor(Date.now() / 1000)) {
      this.db.prepare("DELETE FROM cache WHERE key = ?").run(key);
      return null;
    }
    try {
      return JSON.parse(row.value) as unknown;
    } catch {
      return null;
    }
  }

  async set(key: string, value: unknown, ttlSeconds: number): Promise<void> {
    const expiresAt = Math.floor(Date.now() / 1000) + ttlSeconds;
    this.db
      .prepare(
        "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
      )
      .run(key, JSON.stringify(value), expiresAt);
  }

  async close(): Promise<void> {
    this.db.close();
  }
}
