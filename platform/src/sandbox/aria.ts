/**
 * Text observation of a page for the raw-DOM agent condition: the ARIA snapshot plus a numbered list of
 * interactive elements ([ref=eN]). Refs live in a page-side Map (not DOM attributes) so observing never
 * mutates the page and never pollutes the dom_mutation stream.
 */
import type { ElementHandle, Page } from "playwright";
import { SandboxError } from "./errors.js";

export interface Item {
  ref: string;
  role: string;
  name: string;
  tag: string;
  testid?: string;
  /** `name` attribute of form controls (the field it submits). */
  field?: string;
  inputType?: string;
  min?: number;
  max?: number;
  value?: string;
  options?: string[];
  href?: string;
}

/** Visible interactive elements, numbered e1..eN; also registers the refs used by refHandle(). */
export async function interactiveItems(page: Page): Promise<Item[]> {
  return page.evaluate(() => {
    const refs = new Map<string, Element>();
    (window as unknown as { __specxRefs: Map<string, Element> }).__specxRefs = refs;
    const out: Item[] = [];
    const els = Array.from(document.querySelectorAll("a[href], button, input, select, textarea, [role=button], [role=link]"));
    for (const el of els) {
      const box = el.getBoundingClientRect();
      if (box.width === 0 && box.height === 0) continue;
      const ref = `e${out.length + 1}`;
      refs.set(ref, el);
      const tag = el.tagName.toLowerCase();
      const role = el.getAttribute("role") ?? ({ a: "link", button: "button", select: "combobox", textarea: "textbox" } as Record<string, string>)[tag] ?? (el.getAttribute("type") === "number" ? "spinbutton" : "textbox");
      const label = el.id ? document.querySelector(`label[for="${el.id}"]`)?.textContent : null;
      const name = (el.getAttribute("aria-label") ?? label ?? (el as HTMLElement).innerText ?? "").trim().slice(0, 80);
      const item: Item = { ref, role, name, tag };
      const testid = el.getAttribute("data-testid");
      if (testid) item.testid = testid;
      if (tag === "input" || tag === "textarea" || tag === "select") {
        item.value = (el as HTMLInputElement).value;
        const field = el.getAttribute("name");
        if (field) item.field = field;
        if (tag === "input") item.inputType = el.getAttribute("type") ?? "text";
        if (el.hasAttribute("min")) item.min = Number(el.getAttribute("min"));
        if (el.hasAttribute("max")) item.max = Number(el.getAttribute("max"));
      }
      if (tag === "select") item.options = Array.from((el as HTMLSelectElement).options).map((o) => o.value);
      if (tag === "a") item.href = el.getAttribute("href") ?? "";
      out.push(item);
    }
    return out;
  });
}

export async function observe(page: Page): Promise<string> {
  const items = await interactiveItems(page);
  const tree = await page.locator("body").ariaSnapshot({ timeout: 2000 }).catch(() => "");
  const lines = items.map((i) => {
    let s = `- ${i.role} "${i.name}" [ref=${i.ref}]`;
    if (i.href !== undefined) s += ` href=${i.href}`;
    if (i.value !== undefined) s += ` value="${i.value}"`;
    if (i.options) s += ` options=${i.options.join("|")}`;
    return s;
  });
  return `URL: ${page.url()}\nTitle: ${await page.title()}\n\n${tree}\n\nInteractive elements:\n${lines.join("\n")}`;
}

export async function refHandle(page: Page, ref: string): Promise<ElementHandle> {
  const handle = await page.evaluateHandle((r) => (window as unknown as { __specxRefs?: Map<string, Element> }).__specxRefs?.get(r) ?? null, ref);
  const el = handle.asElement();
  if (!el) throw new SandboxError(400, "unknown_ref", `unknown ref ${ref}; call observe/state again`);
  return el as ElementHandle;
}
