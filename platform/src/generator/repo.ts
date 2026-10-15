/**
 * Code surface of F3: finds Express routes in a seed app's server.js and the SQL each route runs.
 * A small lexer-backed regex parser (tree-sitter has no Node 26 prebuilds; see docs/DECISIONS.md).
 * It reports only what the route code says: work done by triggers or helpers in other files is
 * deliberately invisible here, which is exactly what runtime verification must then catch.
 */
import fs from "node:fs";
import path from "node:path";
import { REPO_ROOT } from "../paths.js";

export type SqlOp = "SELECT" | "INSERT" | "UPDATE" | "DELETE";

export interface SqlStatement {
  sql: string;
  op: SqlOp;
  table: string;
  /** Columns compared with `= ?` in the WHERE clause (alias prefixes stripped). */
  whereCols: string[];
  insertCols: string[];
  insertSelect: boolean;
  sourceTable?: string;
  exec?: "get" | "all" | "run" | null;
}

export interface RouteEvidence {
  method: string;
  path: string;
  file: string;
  line: number;
  snippet: string;
  pathParams: string[];
  bodyFields: string[];
  statements: SqlStatement[];
  tablesWritten: string[];
  tablesRead: string[];
  auditEvent: string | null;
  parser: "regex";
}

const uniq = <T>(xs: T[]): T[] => [...new Set(xs)];

function whereColumns(clause: string | undefined): string[] {
  if (!clause) return [];
  const body = clause.split(/\s+(?:ORDER|GROUP)\s+BY\s+|\s+LIMIT\s+/i)[0] ?? "";
  return body
    .split(/\s+AND\s+/i)
    .map((part) => /^\s*(?:\w+\.)?(\w+)\s*=\s*\?\s*$/.exec(part)?.[1])
    .filter((c): c is string => c !== undefined);
}

export function parseSql(raw: string): SqlStatement | null {
  const sql = raw.replace(/\s+/g, " ").trim();
  const where = (s: string) => /\sWHERE\s(.*)$/i.exec(s)?.[1];
  let m = /^INSERT INTO (\w+)\s*\(([^)]*)\)\s*(VALUES|SELECT)(.*)$/i.exec(sql);
  if (m) {
    const select = (m[3] ?? "").toUpperCase() === "SELECT";
    const rest = m[4] ?? "";
    const s: SqlStatement = { sql, op: "INSERT", table: m[1] as string, insertCols: (m[2] ?? "").split(",").map((c) => c.trim()), insertSelect: select, whereCols: select ? whereColumns(where(rest)) : [] };
    const src = select ? /\sFROM (\w+)/i.exec(rest)?.[1] : undefined;
    if (src) s.sourceTable = src;
    return s;
  }
  m = /^UPDATE (\w+) SET .*$/i.exec(sql);
  if (m) return { sql, op: "UPDATE", table: m[1] as string, whereCols: whereColumns(where(sql)), insertCols: [], insertSelect: false };
  m = /^DELETE FROM (\w+)/i.exec(sql);
  if (m) return { sql, op: "DELETE", table: m[1] as string, whereCols: whereColumns(where(sql)), insertCols: [], insertSelect: false };
  m = /^SELECT .*? FROM (\w+)/i.exec(sql);
  if (m) return { sql, op: "SELECT", table: m[1] as string, whereCols: whereColumns(where(sql)), insertCols: [], insertSelect: false };
  return null;
}

interface Literal {
  start: number;
  end: number; // index just after the closing quote
  value: string;
}

/** Scans JS source for string literals, skipping comments. Good enough for the seed apps' plain JS. */
function literals(src: string): Literal[] {
  const out: Literal[] = [];
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (c === "/" && src[i + 1] === "/") i = src.indexOf("\n", i) === -1 ? src.length : src.indexOf("\n", i);
    else if (c === "/" && src[i + 1] === "*") {
      const end = src.indexOf("*/", i + 2);
      i = end === -1 ? src.length : end + 1;
    }
    else if (c === '"' || c === "'" || c === "`") {
      let j = i + 1;
      while (j < src.length && src[j] !== c) j += src[j] === "\\" ? 2 : 1;
      out.push({ start: i, end: j + 1, value: src.slice(i + 1, j) });
      i = j;
    }
  }
  return out;
}

/** Index just after the parenthesis that closes the one opened at `open`, skipping literals. */
function closeParen(src: string, open: number, lits: Literal[]): number {
  let depth = 0;
  for (let i = open; i < src.length; i++) {
    const lit = lits.find((l) => l.start === i);
    if (lit) {
      i = lit.end - 1;
      continue;
    }
    if (src[i] === "(") depth++;
    else if (src[i] === ")" && --depth === 0) return i + 1;
  }
  return src.length;
}

export function parseRoutes(file: string): RouteEvidence[] {
  const src = fs.readFileSync(file, "utf8");
  const lits = literals(src);
  const rel = path.relative(path.join(REPO_ROOT, "platform"), file);
  const routes: RouteEvidence[] = [];
  const re = /app\.(get|post|put|patch|delete)\(\s*(["'`])([^"'`]+)\2/g;
  for (let m = re.exec(src); m; m = re.exec(src)) {
    const open = src.indexOf("(", m.index);
    const end = closeParen(src, open, lits);
    const body = src.slice(open, end);
    const method = (m[1] as string).toUpperCase();
    const routePath = m[3] as string;
    const statements: SqlStatement[] = [];
    for (const lit of lits.filter((l) => l.start > open && l.end <= end)) {
      const s = parseSql(lit.value);
      if (!s) continue;
      s.exec = (/^\s*\)\s*\.\s*(get|all|run)\(/.exec(src.slice(lit.end, lit.end + 40))?.[1] as SqlStatement["exec"]) ?? null;
      statements.push(s);
    }
    const destructured = [...body.matchAll(/const\s*\{([^}]*)\}\s*=\s*req\.body/g)].flatMap((d) => (d[1] ?? "").split(",").map((f) => f.trim().split(/[\s:=]/)[0] ?? ""));
    const dotted = [...body.matchAll(/req\.body\??\.(\w+)/g)].map((d) => d[1] ?? "");
    routes.push({
      method,
      path: routePath,
      file: rel,
      line: src.slice(0, m.index).split("\n").length,
      snippet: (src.slice(m.index).split("\n")[0] ?? "").trim().slice(0, 200),
      pathParams: [...routePath.matchAll(/:(\w+)/g)].map((p) => p[1] as string),
      bodyFields: uniq([...destructured, ...dotted].filter(Boolean)),
      statements,
      tablesWritten: uniq(statements.filter((s) => s.op !== "SELECT").map((s) => s.table)),
      tablesRead: uniq(statements.flatMap((s) => (s.op === "SELECT" ? [s.table] : s.sourceTable ? [s.sourceTable] : []))),
      auditEvent: /audit\(\s*[\w.]+\s*,\s*["']([\w.]+)["']/.exec(body)?.[1] ?? null,
      parser: "regex",
    });
  }
  return routes;
}
