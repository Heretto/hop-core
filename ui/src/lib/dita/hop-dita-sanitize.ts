/**
 * Allowlist sanitizer for rendered DITA HTML.
 *
 * Angular's built-in `[innerHTML]` sanitizer strips `id`, which rendered DITA
 * depends on: in-topic cross-references, footnote callouts and the
 * `aria-labelledby` that ties each topic to its title all point at ids. This
 * keeps ids and otherwise stays at least as strict as Angular's: a fixed set of
 * presentational elements and attributes, and URLs limited to safe schemes.
 * Parsing uses `DOMParser`, which builds an inert document — nothing in the
 * input runs or loads while it is being cleaned.
 */

/** Elements whose content is dropped along with them. */
const DROP = new Set([
  'script', 'style', 'template', 'iframe', 'frame', 'frameset', 'object', 'embed',
  'applet', 'svg', 'math', 'form', 'input', 'button', 'select', 'textarea', 'option',
  'link', 'meta', 'base', 'noscript', 'head', 'title', 'audio', 'video', 'source',
  'track', 'canvas', 'dialog', 'portal',
]);

/** Elements kept as-is (minus disallowed attributes). Anything else is unwrapped. */
const KEEP = new Set([
  'a', 'abbr', 'article', 'aside', 'b', 'bdi', 'bdo', 'blockquote', 'br', 'caption',
  'cite', 'code', 'col', 'colgroup', 'dd', 'del', 'details', 'dfn', 'div', 'dl', 'dt',
  'em', 'figcaption', 'figure', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hr',
  'i', 'img', 'ins', 'kbd', 'li', 'mark', 'nav', 'ol', 'p', 'pre', 'q', 's', 'samp',
  'section', 'small', 'span', 'strong', 'sub', 'summary', 'sup', 'table', 'tbody',
  'td', 'tfoot', 'th', 'thead', 'time', 'tr', 'u', 'ul', 'var', 'wbr',
]);

const ATTRS = new Set([
  'id', 'class', 'title', 'lang', 'dir', 'role', 'href', 'src', 'alt', 'cite',
  'width', 'height', 'colspan', 'rowspan', 'span', 'scope', 'headers', 'start',
  'reversed', 'type', 'target', 'rel', 'datetime', 'open', 'hreflang',
]);

const URL_ATTRS = new Set(['href', 'src', 'cite']);

/** Relative URLs, fragments, or one of these schemes. */
const SAFE_URL = /^(?:(?:https?|mailto|tel|ftp):|[^a-z]|[a-z][a-z0-9+.-]*(?:[^a-z0-9+.\-:]|$))/i;
const SAFE_DATA_IMAGE = /^data:image\/(?:png|gif|jpe?g|webp|avif);base64,[a-z0-9+/]+=*$/i;

export function isSafeUrl(value: string, attr = 'href'): boolean {
  // Browsers ignore embedded whitespace/control characters in schemes ("java\nscript:").
  const url = value.replace(/[\u0000- \u007f-\u009f]/g, '');
  if (attr === 'src' && url.toLowerCase().startsWith('data:')) return SAFE_DATA_IMAGE.test(url);
  return SAFE_URL.test(url);
}

function clean(node: Node, doc: Document): void {
  for (const child of Array.from(node.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE) continue;
    if (child.nodeType !== Node.ELEMENT_NODE) {
      child.remove(); // comments, processing instructions, CDATA
      continue;
    }
    const el = child as Element;
    const tag = el.localName.toLowerCase();
    if (DROP.has(tag) || el.namespaceURI !== 'http://www.w3.org/1999/xhtml') {
      el.remove();
      continue;
    }
    clean(el, doc);
    if (!KEEP.has(tag)) {
      el.replaceWith(...Array.from(el.childNodes));
      continue;
    }
    for (const attr of Array.from(el.attributes)) {
      const name = attr.name.toLowerCase();
      const allowed = ATTRS.has(name) || name.startsWith('aria-');
      if (!allowed || (URL_ATTRS.has(name) && !isSafeUrl(attr.value, name))) {
        el.removeAttribute(attr.name);
      }
    }
    if (tag === 'a' && el.getAttribute('target') === '_blank') {
      el.setAttribute('rel', 'noopener noreferrer');
    }
  }
}

/** Return a sanitized copy of `html` as a detached fragment of `doc`. */
export function sanitizeDitaHtml(html: string, doc: Document = document): DocumentFragment {
  const parsed = new DOMParser().parseFromString(html, 'text/html');
  clean(parsed.body, parsed);
  const fragment = doc.createDocumentFragment();
  for (const child of Array.from(parsed.body.childNodes)) {
    fragment.appendChild(doc.importNode(child, true));
  }
  return fragment;
}
