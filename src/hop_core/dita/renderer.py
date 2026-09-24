"""DITA topic → HTML5 rendering, modeled on the DITA Open Toolkit's HTML5 transform.

:class:`DitaRenderer` turns a DITA topic (any topic type, nested topics
included) into an HTML fragment an app can put in front of a user::

    from hop_core.dita import DitaRenderer

    result = DitaRenderer().render(dita_xml)
    result.html        # <article class="topic task nested0" ...>...</article>
    result.title       # plain-text title, for page headers and <title>
    result.warnings    # what could not be honored (unresolved keyrefs, ...)

The output follows DITA-OT's HTML5 plugin (``org.dita.html5``): the same
elements, the same ``class`` lists (the element's ``@class`` ancestry plus
``@outputclass`` — ``<uicontrol>`` becomes ``<span class="ph uicontrol">``),
the same ``{topicid}__{elementid}`` ids and the same generated text ("Note:",
"Figure 1. ", "Optional: "). Stylesheets written for DITA-OT output apply, and
``<hop-dita-content>`` in ``@heretto/hop-ui`` styles it with the design system.

Deliberate differences, because the output is a fragment embedded in an app
rather than a standalone page:

* The root topic is an ``<article class="topic … nested0">`` carrying its own
  ``id``, ``lang`` and ``aria-labelledby`` (DITA-OT puts those on ``<html>``
  and ``<body>``).
* No inline ``style`` attributes — sanitizers and strict CSPs drop them.
  Column widths use ``<col width>``; draft comments are classed, not colored.
* Footnote anchors use ``id`` instead of the obsolete ``<a name>``.
* Content that cannot be shown safely inline is dropped with a warning:
  ``<object>``, SVG, MathML and ``<foreign>``.

Every element and attribute in the output is constructed here — nothing from
the source is copied through verbatim — and URLs are restricted to safe
schemes, so the fragment is safe to insert into a page.

References beyond the topic are resolved through hooks, since only the app
knows where the rest of its content lives: ``loader`` fetches other files for
``@conref``, ``keys`` resolves ``@keyref``/``@conkeyref`` (build it from a map
with :func:`keys_from_map`), and ``resolve_href`` maps link and image targets
to URLs the app can serve.
"""

from __future__ import annotations

import copy
import posixpath
import re
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Union

from lxml import etree

from hop_core.dita._classes import DEFAULT_CLASSES

__all__ = [
    "DitaParseError",
    "DitaRenderer",
    "KeyDefinition",
    "RenderedTopic",
    "exclusions_from_ditaval",
    "keys_from_map",
    "render_dita",
]

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

Source = Union[str, bytes, etree._Element]
HrefResolver = Callable[[str, etree._Element], Optional[str]]
Loader = Callable[[str], Union[str, bytes, etree._Element, None]]


class DitaParseError(ValueError):
    """The content is not well-formed XML, or is not something that renders (a map)."""


@dataclass(frozen=True)
class KeyDefinition:
    """What a key resolves to: a target, link text, or both."""

    href: Optional[str] = None
    #: Text for an empty referencing element (``<keyword keyref="product"/>``).
    text: Optional[str] = None
    scope: Optional[str] = None
    format: Optional[str] = None


@dataclass
class RenderedTopic:
    """A rendered topic: the HTML fragment plus plain-text metadata."""

    html: str
    title: str
    shortdesc: Optional[str]
    topic_id: Optional[str]
    #: Root element name: ``topic``, ``concept``, ``task``, ``reference``, ...
    topic_type: str
    lang: Optional[str]
    #: Content that could not be honored, in document order. Rendering still succeeds.
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Generated text (DITA-OT org.dita.base strings-en-us.xml) ─────────────────

NOTE_LABELS = {
    "note": "Note", "tip": "Tip", "fastpath": "Fastpath", "important": "Important",
    "remember": "Remember", "restriction": "Restriction", "attention": "Attention",
    "caution": "CAUTION", "danger": "DANGER", "warning": "Warning",
    "trouble": "Trouble", "notice": "Notice",
}
TASK_LABELS = {
    "task/prereq": "Before you begin", "task/context": "About this task",
    "task/steps": "Procedure", "task/steps-unordered": "Procedure",
    "task/result": "Results", "task/postreq": "What to do next",
    "topic/example": "Example",
}
LINK_GROUPS = [  # (link @type values, title, class), highest priority first
    ({"concept", "glossentry"}, "Related concepts", "relconcepts"),
    ({"task"}, "Related tasks", "reltasks"),
    ({"reference"}, "Related reference", "relref"),
]
TRADEMARKS = {"tm": "™", "reg": "®", "service": "℠"}
# Conditional-processing attributes (DITA 1.3 §2.4.3), plus specializations of @props.
FILTER_ATTRIBUTES = ("props", "audience", "platform", "product", "otherprops", "deliveryTarget")

# Descendants that make a <p> render as <div class="p"> (dita-ot:is-block).
BLOCK_CLASSES = (
    "topic/body", "topic/shortdesc", "topic/abstract", "topic/title", "topic/section",
    "task/info", "topic/p", "topic/pre", "topic/lines", "topic/note", "topic/fig",
    "topic/dl", "topic/sl", "topic/ol", "topic/ul", "topic/li", "topic/sli",
    "topic/itemgroup", "topic/table", "topic/entry", "topic/simpletable",
    "topic/stentry", "topic/example",
)

# Inline elements that are plain HTML tags: most specific class token wins.
INLINE_TAGS = {
    "topic/ph": "span", "topic/keyword": "span", "topic/cite": "cite", "topic/q": "q",
    "topic/term": "dfn", "topic/tm": None, "topic/text": None,
    "hi-d/b": "strong", "hi-d/i": "em", "hi-d/u": "u", "hi-d/sup": "sup", "hi-d/sub": "sub",
    "emphasis-d/em": "em", "emphasis-d/strong": "strong",
    "pr-d/codeph": "code", "sw-d/msgph": "samp", "sw-d/systemoutput": "samp",
    "sw-d/userinput": "kbd", "sw-d/varname": "var",
}

# Elements that never render. Their tails (the text after them) still do.
HIDDEN = {
    "topic/prolog", "topic/titlealts", "topic/metadata", "topic/data", "topic/data-about",
    "topic/foreign", "topic/unknown", "topic/indexterm", "topic/index-base",
    "topic/indextermref", "topic/desc", "topic/navtitle", "topic/searchtitle",
    "topic/no-topic-nesting", "topic/linkinfo", "topic/alt", "pr-d/repsep",
    "hazard-d/hazardsymbol",
}
DROPPED = {  # not renderable inline — warn once per kind
    "topic/object": "<object>", "svg-d/svg-container": "SVG", "mathml-d/mathml": "MathML",
}

MAX_CONREF_DEPTH = 16
CONREF_ATTRIBUTES = ("conref", "conkeyref", "conrefend", "conaction")
# Marks elements whose keyref did not resolve (set during preprocessing, never output).
UNRESOLVED_KEY = "{urn:hop-core:dita}unresolved-key"

_SAFE_URL = re.compile(r"^(?:(?:https?|mailto|tel|ftp):|[^a-z]|[a-z][a-z0-9+.-]*(?:[^a-z0-9+.\-:]|$))", re.I)
_SAFE_DATA_IMAGE = re.compile(r"^data:image/(?:png|gif|jpe?g|webp|avif);base64,[a-z0-9+/]+=*$", re.I)
_URL_NOISE = re.compile(r"[\x00-\x20\x7f-\x9f]")
_XML_DECL = re.compile(r"^\s*<\?xml[^>]*\?>")
_LENGTH = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(px|pt|pc|em|in|cm|mm)?\s*$", re.I)
_PX_PER_UNIT = {"px": 1.0, "pt": 96 / 72, "pc": 16.0, "em": 16.0, "in": 96.0, "cm": 96 / 2.54, "mm": 96 / 25.4}


def _safe_url(url: str, image: bool = False) -> Optional[str]:
    """Return ``url`` if its scheme is safe to put in a page, else None."""
    cleaned = _URL_NOISE.sub("", url)
    if image and cleaned[:5].lower() == "data:":
        return url if _SAFE_DATA_IMAGE.match(cleaned) else None
    return url if _SAFE_URL.match(cleaned) else None


def _to_px(value: Optional[str]) -> Optional[str]:
    """DITA length → integer pixels (DITA-OT ``length-to-pixels``, 96 dpi)."""
    match = _LENGTH.match(value or "")
    if not match:
        return None
    number, unit = float(match.group(1)), (match.group(2) or "px").lower()
    return str(round(number * _PX_PER_UNIT[unit]))


def _text(el: Optional[etree._Element]) -> str:
    """Whitespace-normalized text content, skipping content that never renders."""
    if el is None:
        return ""
    parts: List[str] = []

    def walk(node: etree._Element) -> None:
        if node.text:
            parts.append(node.text)
        for child in node:
            if isinstance(child.tag, str) and not (_tokens(child) and set(_tokens(child)) & HIDDEN):
                walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(el)
    return " ".join("".join(parts).split())


def _local_name(el: etree._Element) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _tokens(el: etree._Element) -> List[str]:
    """The element's ``@class`` tokens, e.g. ``['topic/ph', 'ui-d/uicontrol']``.

    Uses the authored/preprocessed ``@class`` when present, else the DITA 1.3
    DTD default for the element name.
    """
    if not isinstance(el.tag, str) or etree.QName(el).namespace:
        return []
    value = el.get("class") or DEFAULT_CLASSES.get(el.tag, "")
    return [token for token in value.split() if "/" in token]


def _parse(content: Source) -> etree._Element:
    if isinstance(content, etree._Element):
        return copy.deepcopy(content)
    if isinstance(content, str):
        # A str is already decoded; its declaration's encoding no longer applies.
        content = _XML_DECL.sub("", content, count=1).encode("utf-8")
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False,
    )
    try:
        return etree.fromstring(content, parser)
    except etree.XMLSyntaxError as exc:
        raise DitaParseError(f"Not well-formed XML: {exc}") from exc


# ── Public helpers ────────────────────────────────────────────────────────────

def keys_from_map(content: Source) -> Dict[str, KeyDefinition]:
    """Collect key definitions from a DITA map, for :class:`DitaRenderer` ``keys``.

    Reads every element with ``@keys`` (``<keydef>``, ``<topicref>``, ...) in
    document order — the first definition of a key wins, as in DITA. Text comes
    from ``topicmeta/keywords/keyword`` or ``topicmeta/linktext``. Submaps
    (``<mapref>``) and key scopes are not followed; load those maps and merge
    the results yourself.
    """
    root = _parse(content)
    keys: Dict[str, KeyDefinition] = {}
    for el in root.iter():
        if not isinstance(el.tag, str) or not el.get("keys"):
            continue
        text = None
        for meta in el:
            if _local_name(meta) != "topicmeta":
                continue
            keyword = meta.find("keywords/keyword")
            linktext = meta.find("linktext")
            text = _text(keyword) or _text(linktext) or None
        definition = KeyDefinition(
            href=el.get("href"), text=text, scope=el.get("scope"), format=el.get("format"),
        )
        for key in el.get("keys", "").split():
            keys.setdefault(key, definition)
    return keys


def exclusions_from_ditaval(content: Source) -> Dict[str, List[str]]:
    """Read ``<prop action="exclude">`` rules from a DITAVAL file into ``exclude``.

    Flagging and passthrough rules are ignored; so are exclude rules without
    both ``@att`` and ``@val``.
    """
    root = _parse(content)
    exclude: Dict[str, List[str]] = {}
    for prop in root.iter("prop"):
        if prop.get("action") == "exclude" and prop.get("att") and prop.get("val"):
            exclude.setdefault(prop.get("att"), []).append(prop.get("val"))
    return exclude


def render_dita(content: Source, **options) -> RenderedTopic:
    """Render with a one-off :class:`DitaRenderer` — ``render_dita(xml, exclude=...)``."""
    return DitaRenderer(**options).render(content)


# ── Renderer ──────────────────────────────────────────────────────────────────

class DitaRenderer:
    """Renders DITA topics to HTML fragments. Stateless and reusable across threads.

    Args:
        resolve_href: ``(href, element) -> url | None`` for every link and image
            target that is not a fragment of the same topic. ``element`` is the
            source ``<xref>``, ``<link>``, ``<image>``, ... so ``@scope`` and
            ``@format`` are at hand. Return None to drop the link (its text
            stays) or the image. Without it, hrefs follow DITA-OT: DITA targets
            get an ``.html`` extension, everything else passes through.
        loader: ``(path) -> xml | None`` fetching another file for ``@conref``.
            Paths are resolved relative to the referencing file and normalized.
            Without it, only same-file conrefs resolve.
        keys: Key name → :class:`KeyDefinition` (see :func:`keys_from_map`).
        exclude: Conditional processing, e.g. ``{"audience": ["expert"]}``. An
            element is removed when every value of one of its filter attributes
            is excluded — the DITAVAL rule. Grouped values
            (``product="db(a b)"``) are matched under the group name.
        show_draft: Render ``<draft-comment>`` and ``<required-cleanup>``.
        task_labels: Emit DITA-OT's generated task headings ("Before you begin",
            "Procedure", ...). Off by default, as in DITA-OT.
        heading_offset: Push every heading down this many levels, to fit the
            topic under the host page's own headings. 1 makes the title an h2.
    """

    def __init__(
        self,
        *,
        resolve_href: Optional[HrefResolver] = None,
        loader: Optional[Loader] = None,
        keys: Optional[Mapping[str, Union[KeyDefinition, Mapping[str, str]]]] = None,
        exclude: Optional[Mapping[str, Iterable[str]]] = None,
        show_draft: bool = False,
        task_labels: bool = False,
        heading_offset: int = 0,
    ):
        self.resolve_href = resolve_href
        self.loader = loader
        self.keys: Dict[str, KeyDefinition] = {
            name: value if isinstance(value, KeyDefinition) else KeyDefinition(**value)
            for name, value in (keys or {}).items()
        }
        self.exclude: Dict[str, frozenset] = {
            name: frozenset(values) for name, values in (exclude or {}).items() if values
        }
        self.show_draft = show_draft
        self.task_labels = task_labels
        self.heading_offset = max(0, int(heading_offset))

    def render(self, content: Source) -> RenderedTopic:
        """Render a topic (or a ``<dita>`` container, or a bare element) to HTML.

        Raises :class:`DitaParseError` for XML that is not well-formed, and for maps.
        """
        root = _parse(content)
        if "map/map" in _tokens(root):
            raise DitaParseError("This is a DITA map, not a topic — render its topics instead.")
        return _Render(self, root).run()


class _Render:
    """State for one render: counters, footnotes, warnings."""

    def __init__(self, options: DitaRenderer, root: etree._Element):
        self.o = options
        self.root = root
        self.warnings: List[str] = []
        self.title_count = 0
        self.fig_count = 0
        self.table_count = 0
        self.trademarks_seen: set = set()
        self.docs: Dict[str, etree._Element] = {"": copy.deepcopy(root)}
        self.footnotes: List[etree._Element] = []
        self.fn_numbers: Dict[etree._Element, int] = {}
        self.dropped_kinds: set = set()

    # ── Driver ────────────────────────────────────────────────────────────────

    def run(self) -> RenderedTopic:
        root = self.root
        self.resolve_conrefs(root, "", 0)
        self.filter(root)
        self.resolve_keyrefs(root)
        self.number_footnotes(root)

        if self.is_(root, "topic/topic"):
            nodes = self.render(root)
            topics = [root]
        elif _local_name(root) == "dita":
            nodes = [n for child in root if self.is_(child, "topic/topic") for n in self.render(child)]
            topics = [child for child in root if self.is_(child, "topic/topic")]
            nodes.extend(self.endnotes())
        else:
            nodes = self.render(root) + self.endnotes()
            topics = []

        html = "".join(
            node if isinstance(node, str) else etree.tostring(node, method="html", encoding="unicode")
            for node in nodes
        )
        first = topics[0] if topics else None
        title = self.first_child(first, "topic/title") if first is not None else None
        shortdesc = self.find_shortdesc(first) if first is not None else None
        lang = (first if first is not None else root).get(XML_LANG)
        return RenderedTopic(
            html=html,
            title=_text(title),
            shortdesc=_text(shortdesc) or None,
            topic_id=first.get("id") if first is not None else root.get("id"),
            topic_type=_local_name(first if first is not None else root),
            lang=lang,
            warnings=list(dict.fromkeys(self.warnings)),
        )

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    # ── Class helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def is_(el: Optional[etree._Element], token: str) -> bool:
        return el is not None and token in _tokens(el)

    def first_child(self, el: etree._Element, token: str) -> Optional[etree._Element]:
        for child in el:
            if self.is_(child, token):
                return child
        return None

    def find_shortdesc(self, topic: etree._Element) -> Optional[etree._Element]:
        direct = self.first_child(topic, "topic/shortdesc")
        if direct is not None:
            return direct
        abstract = self.first_child(topic, "topic/abstract")
        return self.first_child(abstract, "topic/shortdesc") if abstract is not None else None

    def topic_of(self, el: etree._Element) -> Optional[etree._Element]:
        for ancestor in el.iterancestors():
            if self.is_(ancestor, "topic/topic"):
                return ancestor
        return None

    def prefixed_id(self, el: etree._Element, value: Optional[str] = None) -> Optional[str]:
        """DITA-OT ids: topics keep theirs; elements become ``{topicid}__{id}``."""
        value = value if value is not None else el.get("id")
        if not value:
            return None
        if self.is_(el, "topic/topic"):
            return value
        topic = self.topic_of(el)
        return f"{topic.get('id')}__{value}" if topic is not None and topic.get("id") else value

    def fragment(self, frag: str) -> str:
        """``topicid/elemid`` → ``topicid__elemid`` (the rendered id)."""
        topic_id, _, elem_id = frag.partition("/")
        return f"{topic_id}__{elem_id}" if elem_id else topic_id

    def level(self, el: etree._Element) -> int:
        """Heading level: enclosing topics plus titled sections/examples."""
        n = 0
        for node in [el, *el.iterancestors()]:
            if self.is_(node, "topic/topic"):
                n += 1
            elif (self.is_(node, "topic/section") or self.is_(node, "topic/example")) and (
                self.first_child(node, "topic/title") is not None or node.get("spectitle")
            ):
                n += 1
        return max(1, min(6, n))

    def heading(self, level: int) -> str:
        return f"h{min(6, level + self.o.heading_offset)}"

    # ── Output helpers ────────────────────────────────────────────────────────

    def element(self, tag: str, src: Optional[etree._Element] = None, extra: Sequence[str] = (),
                ancestry: bool = True, with_id: bool = True) -> etree._Element:
        """An output element carrying DITA-OT's common attributes for ``src``."""
        out = etree.Element(tag)
        classes: List[str] = []
        if src is not None:
            if src.get(XML_LANG):
                out.set("lang", src.get(XML_LANG))
            if src.get("dir") in ("ltr", "rtl", "auto"):
                out.set("dir", src.get("dir"))
            if ancestry:
                classes.extend(token.split("/", 1)[1] for token in _tokens(src))
        classes.extend(extra)
        if src is not None:
            classes.extend((src.get("outputclass") or "").split())
        classes = [c for c in dict.fromkeys(classes) if c]
        if classes:
            out.set("class", " ".join(classes))
        if src is not None and with_id:
            element_id = self.prefixed_id(src)
            if element_id:
                out.set("id", element_id)
        return out

    @staticmethod
    def add(out: etree._Element, node: Union[etree._Element, str, None]) -> None:
        if node is None or node == "":
            return
        if isinstance(node, str):
            if len(out):
                out[-1].tail = (out[-1].tail or "") + node
            else:
                out.text = (out.text or "") + node
        else:
            out.append(node)

    def add_all(self, out: etree._Element, nodes: Iterable[Union[etree._Element, str]]) -> etree._Element:
        for node in nodes:
            self.add(out, node)
        return out

    def children(self, src: etree._Element, skip: Callable[[etree._Element], bool] = lambda _: False
                 ) -> List[Union[etree._Element, str]]:
        """Render ``src``'s content (text, children, tails) in order."""
        nodes: List[Union[etree._Element, str]] = []
        if src.text:
            nodes.append(src.text)
        for child in src:
            if isinstance(child.tag, str) and not skip(child):
                nodes.extend(self.render(child))
            if child.tail:
                nodes.append(child.tail)
        return nodes

    def wrap(self, tag: str, src: etree._Element, extra: Sequence[str] = (), **kw) -> List:
        return [self.add_all(self.element(tag, src, extra, **kw), self.children(src))]

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def render(self, el: etree._Element) -> List[Union[etree._Element, str]]:
        if not isinstance(el.tag, str):
            return []
        if etree.QName(el).namespace:
            self.drop(f"<{etree.QName(el).localname}> in namespace {etree.QName(el).namespace}")
            return []
        tokens = _tokens(el)
        for token in reversed(tokens):
            if token in HIDDEN:
                return []
            if token in DROPPED:
                self.drop(DROPPED[token])
                return []
            handler = HANDLERS.get(token)
            if handler is not None:
                return handler(self, el)
            if token in INLINE_TAGS:
                return self.inline(el, INLINE_TAGS[token])
        if tokens:
            return self.wrap("span", el)
        self.warn(f"Unknown element <{el.tag}> rendered as plain text")
        return self.wrap("span", el, ["undefined_element"], ancestry=False)

    def drop(self, kind: str) -> None:
        if kind not in self.dropped_kinds:
            self.dropped_kinds.add(kind)
            self.warn(f"{kind} content is not rendered")

    # ── Preprocessing: conref, filtering, keyref, footnotes ───────────────────

    def load(self, path: str) -> Optional[etree._Element]:
        if path in self.docs:
            return self.docs[path]
        doc = None
        if self.o.loader is not None:
            try:
                loaded = self.o.loader(path)
                doc = _parse(loaded) if loaded is not None else None
            except DitaParseError as exc:
                self.warn(f"Could not parse {path} for conref: {exc}")
            except Exception as exc:  # the app's loader failing must not fail the render
                self.warn(f"Could not load {path} for conref: {exc}")
        self.docs[path] = doc
        return doc

    def find_target(self, href: str, base: str):
        """Resolve a conref href to (element, the file it lives in)."""
        path, _, frag = href.partition("#")
        if path:
            path = posixpath.normpath(posixpath.join(posixpath.dirname(base), path)) if base else path
        else:
            path = base
        doc = self.load(path)
        if doc is None:
            return None, path
        if not frag:
            return doc, path
        topic_id, _, elem_id = frag.partition("/")
        scope = doc if doc.get("id") == topic_id else next(iter(doc.xpath(".//*[@id=$id]", id=topic_id)), None)
        if scope is None:
            return None, path
        if not elem_id:
            return scope, path
        return next(iter(scope.xpath(".//*[@id=$id]", id=elem_id)), None), path

    def resolve_conrefs(self, el: etree._Element, base: str, depth: int) -> None:
        for child in list(el):
            if not isinstance(child.tag, str):
                continue
            if child.get("conref") or child.get("conkeyref"):
                replacement = self.pull_conref(child, base, depth)
                if replacement is not None:
                    el.replace(child, replacement)
                    continue
            self.resolve_conrefs(child, base, depth)

    def pull_conref(self, el: etree._Element, base: str, depth: int) -> Optional[etree._Element]:
        href = el.get("conref")
        if el.get("conkeyref"):
            key, _, elem_id = el.get("conkeyref").partition("/")
            definition = self.o.keys.get(key)
            if definition is not None and definition.href:
                path, _, topic_frag = definition.href.partition("#")
                if elem_id:
                    topic_id = topic_frag.split("/")[0] if topic_frag else self.root_topic_id(path, base)
                    href = f"{path}#{topic_id}/{elem_id}" if topic_id else None
                else:
                    href = definition.href
            elif not href:
                self.warn(f"Unresolved conkeyref '{el.get('conkeyref')}'")
                return None
        if el.get("conaction"):
            self.warn(f"conaction='{el.get('conaction')}' (conref push) is not supported")
            return None
        if depth >= MAX_CONREF_DEPTH:
            self.warn(f"Conref '{href}' nests too deeply (circular reference?)")
            return None
        target, target_base = self.find_target(href, base) if href else (None, base)
        if target is None:
            self.warn(f"Unresolved conref '{href}'")
            return None
        if el.get("conrefend"):
            self.warn(f"conrefend ranges are not supported; used only the start of '{href}'")
        pulled = copy.deepcopy(target)
        if pulled.get("conref") or pulled.get("conkeyref"):
            # The target is itself a reference: follow the chain (the depth cap catches cycles).
            pulled = self.pull_conref(pulled, target_base, depth + 1)
            if pulled is None:
                return None
        pulled.tag = el.tag
        pulled.tail = el.tail
        for name in ("id", *CONREF_ATTRIBUTES):
            pulled.attrib.pop(name, None)
        for name, value in el.attrib.items():
            if name not in CONREF_ATTRIBUTES and value != "-dita-use-conref-target":
                pulled.set(name, value)
        self.resolve_conrefs(pulled, target_base, depth + 1)
        return pulled

    def root_topic_id(self, path: str, base: str) -> Optional[str]:
        target, _ = self.find_target(path, base)
        return target.get("id") if target is not None else None

    def excluded(self, el: etree._Element) -> bool:
        if not self.o.exclude:
            return False
        for attribute in {*FILTER_ATTRIBUTES, *self.o.exclude}:
            raw = el.get(attribute)
            if not raw:
                continue
            groups: Dict[str, List[str]] = {}
            for name, values in re.findall(r"([\w.-]+)\(([^)]*)\)", raw):
                groups.setdefault(name, []).extend(values.split())
            bare = re.sub(r"[\w.-]+\([^)]*\)", " ", raw).split()
            if bare:
                groups.setdefault(attribute, []).extend(bare)
            for name, values in groups.items():
                rule = self.o.exclude.get(name)
                if rule and values and all(value in rule for value in values):
                    return True
        return False

    def filter(self, el: etree._Element) -> None:
        for child in list(el):
            if not isinstance(child.tag, str):
                continue
            if self.excluded(child):
                self.remove(child)
            else:
                self.filter(child)

    @staticmethod
    def remove(el: etree._Element) -> None:
        """Remove ``el``, keeping the text that follows it."""
        parent, tail = el.getparent(), el.tail
        if tail:
            previous = el.getprevious()
            if previous is not None:
                previous.tail = (previous.tail or "") + tail
            else:
                parent.text = (parent.text or "") + tail
        parent.remove(el)

    def resolve_keyrefs(self, root: etree._Element) -> None:
        for el in root.iter():
            if not isinstance(el.tag, str) or not el.get("keyref"):
                continue
            key = el.get("keyref").split("/", 1)[0]
            definition = self.o.keys.get(key)
            if definition is None:
                el.set(UNRESOLVED_KEY, key)
                self.warn(f"Unresolved keyref '{el.get('keyref')}'")
                continue
            if definition.href and not el.get("href"):
                el.set("href", definition.href)
                for name in ("scope", "format"):
                    if getattr(definition, name) and not el.get(name):
                        el.set(name, getattr(definition, name))
            empty = not (el.text or "").strip() and not len(el)
            if empty and definition.text:
                el.text = definition.text

    def number_footnotes(self, root: etree._Element) -> None:
        n = 0
        for el in root.iter():
            if self.is_(el, "topic/fn") and not self.inside_hidden_draft(el):
                n += 1
                self.fn_numbers[el] = n

    def inside_hidden_draft(self, el: etree._Element) -> bool:
        if self.o.show_draft:
            return False
        return any(
            self.is_(a, "topic/draft-comment") or self.is_(a, "topic/required-cleanup")
            for a in el.iterancestors()
        )

    # ── Links ─────────────────────────────────────────────────────────────────

    def final_href(self, el: etree._Element, href: str, image: bool = False) -> Optional[str]:
        """DITA-OT ``determine-final-href``, then the app's resolver, then the safety check."""
        href = href.strip()
        if href.startswith("#"):
            return "#" + self.fragment(href[1:])
        if self.o.resolve_href is not None:
            resolved = self.o.resolve_href(href, el)
            return _safe_url(resolved, image) if resolved is not None else None
        fmt, scope = (el.get("format") or "").lower(), el.get("scope")
        if image or (fmt and fmt != "dita") or (not fmt and scope == "external"):
            return _safe_url(href, image)
        path, _, frag = href.partition("#")
        name = path.rsplit("/", 1)[-1]
        if "." in name:
            path = path[: path.rfind(".")] + ".html"
        return _safe_url(path + ("#" + self.fragment(frag) if frag else ""))

    def is_external(self, el: etree._Element) -> bool:
        fmt = (el.get("format") or "").lower()
        return (
            el.get("scope") == "external" or el.get("type") == "external"
            or (fmt == "pdf" and el.get("scope") != "local")
        )

    def anchor(self, el: etree._Element, href: str, extra: Sequence[str] = ()) -> etree._Element:
        a = self.element("a", el, extra, ancestry=False, with_id=False)
        a.set("href", href)
        if self.is_external(el):
            a.set("target", "_blank")
            a.set("rel", "external noopener")
        return a

    def local_target_text(self, href: str) -> Optional[str]:
        """Title text of a same-document target, for an empty xref."""
        if not href.startswith("#"):
            return None
        topic_id, _, elem_id = href[1:].partition("/")
        matches = self.root.xpath(".//*[@id=$id] | self::*[@id=$id]", id=topic_id)
        target = matches[0] if matches else None
        if target is not None and elem_id:
            found = target.xpath(".//*[@id=$id]", id=elem_id)
            target = found[0] if found else None
        if target is None:
            return None
        title = self.first_child(target, "topic/title")
        return _text(title) or None

    # ── Topic structure ───────────────────────────────────────────────────────

    def topic(self, el: etree._Element) -> List:
        depth = sum(1 for a in el.iterancestors() if self.is_(a, "topic/topic"))
        article = self.element("article", el, [f"nested{min(depth, 9)}"])
        body = self.first_child(el, "topic/body")
        title = self.first_child(el, "topic/title")
        if title is not None:
            self.title_count += 1
            title_id = self.prefixed_id(title) or f"ariaid-title{self.title_count}"
            article.set("aria-labelledby", title_id)
            level = self.level(el)
            h = self.element(self.heading(level), title, [f"topictitle{level}"], with_id=False)
            h.set("id", title_id)
            self.add_all(h, self.children(title))
        intro = [c for c in el if self.is_(c, "topic/abstract") or self.is_(c, "topic/shortdesc")]
        for child in el:
            if not isinstance(child.tag, str):
                continue
            if child is title:
                article.append(h)
            elif any(child is c for c in intro):
                if body is None:
                    self.add_all(article, self.render(child))
            elif child is body:
                div = self.wrap("div", body)[0]
                # DITA-OT moves abstract and shortdesc to the top of the body.
                prefix = [n for c in intro for n in self.render(c) if not isinstance(n, str)]
                for index, node in enumerate(prefix):
                    div.insert(index, node)
                if prefix:
                    prefix[-1].tail = div.text
                    div.text = None
                article.append(div)
            else:
                self.add_all(article, self.render(child))
        if el is self.root:
            self.add_all(article, self.endnotes())
        return [article]

    def title(self, el: etree._Element) -> List:
        return self.wrap("span", el)

    def shortdesc(self, el: etree._Element) -> List:
        parent = el.getparent()
        if self.is_(parent, "topic/abstract"):
            has_blocks = any(
                any(self.is_(sibling, token) for token in BLOCK_CLASSES)
                for sibling in parent if sibling is not el
            )
            if not has_blocks:
                nodes = self.wrap("span", el, with_id=False)
                return ([" "] if el.getprevious() is not None or (parent.text or "").strip() else []) + nodes
        return self.wrap("p", el, with_id=False)

    def section(self, el: etree._Element) -> List:
        in_task = self.is_(el, "topic/example") and self.is_(el.getparent(), "task/taskbody")
        tag = "div" if self.is_(el, "topic/example") and not in_task else "section"
        out = self.element(tag, el)
        title = self.first_child(el, "topic/title")
        level = self.level(el)
        if title is not None:
            self.add_all(self.sub(out, self.heading(level), "title sectiontitle"), self.children(title))
        elif el.get("spectitle"):
            self.sub(out, self.heading(level), "sectiontitle").text = el.get("spectitle")
        elif self.o.task_labels:
            self.task_label(el, out)
        self.add_all(out, self.children(el, skip=lambda c: c is title))
        return [out]

    def task_label(self, el: etree._Element, out: etree._Element) -> None:
        if self.is_(el, "topic/example") and not self.is_(el.getparent(), "task/taskbody"):
            return
        label = next((TASK_LABELS[t] for t in reversed(_tokens(el)) if t in TASK_LABELS), None)
        if label:
            wrapper = self.sub(out, "div", "tasklabel")
            self.sub(wrapper, self.heading(self.level(el) + 1), "sectiontitle tasklabel").text = label

    @staticmethod
    def sub(parent: etree._Element, tag: str, cls: Optional[str] = None) -> etree._Element:
        child = etree.SubElement(parent, tag)
        if cls:
            child.set("class", cls)
        return child

    def div(self, el: etree._Element) -> List:
        return self.wrap("div", el)

    def abstract(self, el: etree._Element) -> List:
        return self.wrap("div", el, with_id=False)

    def related_links(self, el: etree._Element) -> List:
        nav = self.element("nav", el, with_id=False)
        nav.set("role", "navigation")
        def in_linklist(node: etree._Element) -> bool:
            return any(self.is_(a, "topic/linklist") for a in node.iterancestors())

        links = [link for link in el.iter() if self.is_(link, "topic/link") and not in_linklist(link)]
        child_links = [l for l in links if l.get("role") in ("child", "descendant")]
        family = [l for l in links if l.get("role") in ("parent", "previous", "next")]
        others = [l for l in links if l not in child_links and l not in family]

        if child_links:
            ul = self.sub(nav, "ul", "ullinks")
            for link in child_links:
                li = self.sub(ul, "li", "link ulchildlink")
                a = self.link_anchor(link)
                if a is not None:
                    self.sub(li, "strong").append(a)
                desc = self.first_child(link, "topic/desc")
                if desc is not None:
                    self.sub(li, "br")
                    self.add_all(li, self.children(desc))
        if family:
            box = self.sub(nav, "div", "familylinks")
            for role, label in (("parent", "Parent topic"), ("previous", "Previous topic"), ("next", "Next topic")):
                for link in (l for l in family if l.get("role") == role):
                    a = self.link_anchor(link)
                    if a is None:
                        continue
                    row = self.sub(box, "div", f"{role}link")
                    self.sub(row, "strong").text = f"{label}:"
                    self.add(row, " ")
                    row.append(a)
        groups = [(types, title, cls, []) for types, title, cls in LINK_GROUPS]
        rest: List[etree._Element] = []
        seen: set = set()
        for link in others:
            if link.get("href") in seen and link.get("href"):
                continue
            seen.add(link.get("href"))
            bucket = next((g[3] for g in groups if link.get("type") in g[0]), rest)
            bucket.append(link)
        for _, title, cls, members in [*groups, (None, "Related information", "relinfo", rest)]:
            anchors = [a for a in (self.link_anchor(l) for l in members) if a is not None]
            if not anchors:
                continue
            box = self.sub(nav, "div", f"linklist {cls}")
            self.sub(box, "strong").text = title
            self.sub(box, "br")
            ul = self.sub(box, "ul", "linklist")
            for a in anchors:
                self.sub(ul, "li", "linklist").append(a)
        for linklist in (c for c in el.iter() if self.is_(c, "topic/linklist") and not in_linklist(c)):
            nav.append(self.linklist(linklist, nested=False))
        return [nav] if len(nav) else []

    def linklist(self, el: etree._Element, nested: bool) -> etree._Element:
        box = self.element("div", el, ["sublinklist" if nested else "linklist"], ancestry=False, with_id=False)
        title = self.first_child(el, "topic/title")
        if title is not None:
            self.add_all(self.sub(box, "strong"), self.children(title))
            self.sub(box, "br")
        desc = self.first_child(el, "topic/desc")
        if desc is not None:
            self.add_all(box, self.children(desc))
            self.sub(box, "br")
        ul = self.sub(box, "ul", "linklist")
        for child in el:
            if self.is_(child, "topic/link"):
                a = self.link_anchor(child)
                if a is not None:
                    self.sub(ul, "li", "linklist").append(a)
            elif self.is_(child, "topic/linklist"):
                self.sub(ul, "li", "sublinklist").append(self.linklist(child, nested=True))
        info = self.first_child(el, "topic/linkinfo")
        if info is not None:
            self.add_all(box, self.children(info))
            self.sub(box, "br")
        return box

    def link_anchor(self, link: etree._Element) -> Optional[etree._Element]:
        href = link.get("href")
        if not href:
            return None
        final = self.final_href(link, href)
        linktext = self.first_child(link, "topic/linktext")
        if final is None:
            return None
        a = self.anchor(link, final, ["link"])
        if linktext is not None:
            self.add_all(a, self.children(linktext))
        else:
            a.text = self.local_target_text(href) or (
                href[len("mailto:"):] if href.startswith("mailto:") else final
            )
        desc = self.first_child(link, "topic/desc")
        if desc is not None and _text(desc):
            a.set("title", _text(desc))
        return a

    def link(self, el: etree._Element) -> List:
        a = self.link_anchor(el)
        return [a] if a is not None else []

    # ── Block elements ────────────────────────────────────────────────────────

    def p(self, el: etree._Element) -> List:
        block = any(
            self.is_(d, token) for d in el.iterdescendants() for token in BLOCK_CLASSES
        ) or any(
            self.is_(d, "topic/image") and d.get("placement") == "break" for d in el.iterdescendants()
        )
        return self.wrap("div" if block else "p", el)

    def lq(self, el: etree._Element) -> List:
        out = self.wrap("blockquote", el)[0]
        href, reftitle = el.get("href"), el.get("reftitle")
        if href or reftitle:
            self.sub(out, "br")
            box = self.sub(out, "div")
            final = self.final_href(el, href) if href else None
            if final:
                a = self.anchor(el, final)
                box.append(a)
                self.sub(a, "cite").text = reftitle or href
            else:
                self.sub(box, "cite").text = reftitle or href
        return [out]

    def note(self, el: etree._Element) -> List:
        kind = el.get("type") or "note"
        if kind == "other":
            label, kind = el.get("othertype") or "Note", "note"
        elif kind in NOTE_LABELS:
            label = NOTE_LABELS[kind]
        else:
            label, kind = "Note", "note"
        nodes = self.spectitle(el)
        out = self.element("div", el, [kind, f"note_{kind}"])
        self.sub(out, "span", "note__title").text = f"{label}:"
        self.add(out, " ")
        self.add_all(self.sub(out, "div", "note__body"), self.children(el))
        return nodes + [out]

    def spectitle(self, el: etree._Element) -> List:
        if not el.get("spectitle"):
            return []
        box = etree.Element("div", {"class": "spectitle"})
        self.sub(box, "strong").text = el.get("spectitle")
        return [box]

    def pre(self, el: etree._Element) -> List:
        frame = el.get("frame") or ""
        nodes = [etree.Element("hr")] if frame in ("top", "topbot", "all") else []
        nodes += self.spectitle(el) + self.wrap("pre", el)
        if frame in ("bottom", "topbot", "all"):
            nodes.append(etree.Element("hr"))
        return nodes

    def codeblock(self, el: etree._Element) -> List:
        out = self.element("pre", el)
        self.add_all(self.sub(out, "code"), self.children(el))
        return self.spectitle(el) + [out]

    def lines(self, el: etree._Element) -> List:
        out = self.wrap("p", el)[0]
        self.break_lines(out)
        return self.spectitle(el) + [out]

    def break_lines(self, node: etree._Element) -> None:
        """Newlines → ``<br>``, double spaces → no-break spaces, as DITA-OT does for ``<lines>``."""
        def split(text: str):
            first, *rest = text.replace("  ", "\u00a0\u00a0").split("\n")
            breaks = []
            for line in rest:
                br = etree.Element("br")
                br.tail = line or None
                breaks.append(br)
            return first or None, breaks

        for child in list(node):
            self.break_lines(child)
            if child.tail:
                child.tail, breaks = split(child.tail)
                position = node.index(child) + 1
                for offset, br in enumerate(breaks):
                    node.insert(position + offset, br)
        if node.text:
            node.text, breaks = split(node.text)
            for offset, br in enumerate(breaks):
                node.insert(offset, br)

    def fig(self, el: etree._Element) -> List:
        frame = {"all": "figborder", "sides": "figsides", "top": "figtop",
                 "bottom": "figbottom", "topbot": "figtopbot"}.get(el.get("frame") or "", "fignone")
        out = self.element("figure", el, [frame])
        title = self.first_child(el, "topic/title")
        desc = self.first_child(el, "topic/desc")
        if title is not None:
            self.fig_count += 1
            caption = self.sub(out, "figcaption")
            self.sub(caption, "span", "fig--title-label").text = f"Figure {self.fig_count}. "
            self.add_all(caption, self.children(title))
            if desc is not None:
                self.add(caption, ". ")
                caption.append(self.add_all(self.element("span", desc, ["figdesc"]), self.children(desc)))
        elif desc is not None:
            caption = self.sub(out, "figcaption", "desc figdesc")
            self.add_all(caption, self.children(desc))
        self.add_all(out, self.children(el, skip=lambda c: c is title or c is desc))
        return [out]

    def figgroup(self, el: etree._Element) -> List:
        return self.wrap("div", el)

    def image(self, el: etree._Element) -> List:
        if el.get(UNRESOLVED_KEY) and not el.get("href"):
            return []
        href = el.get("href")
        src = self.final_href(el, href, image=True) if href else None
        if not src:
            if href:
                self.warn(f"Image '{href}' has no usable URL")
            return []
        align = el.get("align") if el.get("align") in ("left", "right", "center") else None
        placement = el.get("placement") or "inline"
        img = self.element("img", el, [f"image{align}"] if align and placement == "break" else [])
        img.set("src", src)
        for name in ("height", "width"):
            px = _to_px(el.get(name))
            if px:
                img.set(name, px)
        alt_el = self.first_child(el, "topic/alt")
        alt = _text(alt_el) if alt_el is not None else el.get("alt")
        if alt is not None:
            img.set("alt", alt)
        if el.get("scope") == "external":
            img.set("loading", "lazy")
        if placement != "break":
            return [img]
        if align:
            wrapper = etree.Element("div", {"class": f"image{align}"})
            wrapper.append(img)
            return [wrapper]
        return [etree.Element("br"), img, etree.Element("br")]

    def ul(self, el: etree._Element, extra: Sequence[str] = ()) -> List:
        if not any(self.is_(c, "topic/li") or self.is_(c, "topic/sli") for c in el):
            return []
        classes = [*extra, *(["compact"] if el.get("compact") == "yes" else [])]
        return self.wrap("ul", el, classes)

    def sl(self, el: etree._Element) -> List:
        return self.ul(el, ["simple"])

    def ol(self, el: etree._Element) -> List:
        if not any(self.is_(c, "topic/li") for c in el):
            return []
        out = self.wrap("ol", el, ["compact"] if el.get("compact") == "yes" else [])[0]
        depth = sum(1 for a in [el, *el.iterancestors()] if self.is_(a, "topic/ol"))
        list_type = {2: "a", 0: "i"}.get(depth % 3)
        if list_type:
            out.set("type", list_type)
        return [out]

    def li(self, el: etree._Element) -> List:
        expand = ["liexpand"] if el.getparent() is not None and el.getparent().get("compact") == "no" else []
        return self.wrap("li", el, expand)

    def sli(self, el: etree._Element) -> List:
        return self.wrap("li", el)

    def itemgroup(self, el: etree._Element) -> List:
        # Task item groups (info, stepxmp, stepresult, tutorialinfo) are blocks;
        # a generic itemgroup is just its content.
        if any(t in ("task/info", "task/stepxmp", "task/stepresult", "task/tutorialinfo") for t in _tokens(el)):
            return self.wrap("div", el)
        return self.children(el)

    def dl(self, el: etree._Element) -> List:
        if not any(self.is_(c, "topic/dlentry") for c in el):
            return []
        return self.wrap("dl", el, ["compact"] if el.get("compact") == "yes" else [])

    def dlentry(self, el: etree._Element) -> List:
        nodes: List = []
        compact_no = el.getparent() is not None and el.getparent().get("compact") == "no"
        first_dt, dd_count = True, 0
        for child in el:
            if self.is_(child, "topic/dt"):
                out = self.wrap("dt", child, ["dlterm", *(["dltermexpand"] if compact_no and first_dt else [])])[0]
                if el.get(XML_LANG) and not out.get("lang"):
                    out.set("lang", el.get(XML_LANG))
                if first_dt and el.get("id"):
                    entry_id = self.prefixed_id(el)
                    if out.get("id"):
                        self.sub(out, "a").set("id", entry_id)
                    else:
                        out.set("id", entry_id)
                first_dt = False
                nodes.append(out)
            elif self.is_(child, "topic/dd"):
                dd_count += 1
                nodes.extend(self.wrap("dd", child, ["ddexpand"] if dd_count > 1 else []))
            elif isinstance(child.tag, str):
                nodes.extend(self.render(child))
        return nodes

    def dlhead(self, el: etree._Element) -> List:
        nodes: List = []
        for child in el:
            if self.is_(child, "topic/dthd") or self.is_(child, "topic/ddhd"):
                tag = "dt" if self.is_(child, "topic/dthd") else "dd"
                out = self.element(tag, child)
                self.add_all(self.sub(out, "strong"), self.children(child))
                nodes.append(out)
        return nodes

    def draft(self, el: etree._Element, label: str, meta: Sequence[Optional[str]]) -> List:
        if not self.o.show_draft:
            return []
        out = self.element("div", el)
        self.sub(out, "strong").text = f"{label}: "
        details = " ".join(m for m in meta if m)
        if details:
            self.add(out, details)
        self.sub(out, "br")
        return [self.add_all(out, self.children(el))]

    def draft_comment(self, el: etree._Element) -> List:
        return self.draft(el, "Draft comment", [el.get("author"), el.get("disposition"), el.get("time")])

    def required_cleanup(self, el: etree._Element) -> List:
        return self.draft(el, "Required cleanup", [f"[{el.get('remap')}]" if el.get("remap") else None])

    # ── Footnotes ─────────────────────────────────────────────────────────────

    def fn(self, el: etree._Element) -> List:
        if el not in self.fn_numbers:
            return []
        self.footnotes.append(el)
        if el.get("id"):
            return []  # reached through <xref type="fn">
        n = self.fn_numbers[el]
        a = etree.Element("a", {"id": f"fnsrc_{n}", "href": f"#fntarg_{n}", "class": "fn-callout"})
        self.sub(a, "sup").text = el.get("callout") or str(n)
        return [a]

    def endnotes(self) -> List:
        nodes: List = []
        for el in self.footnotes:
            n = self.fn_numbers[el]
            out = self.element("div", el, with_id=False)
            out.set("class", " ".join(["fn", *(el.get("outputclass") or "").split()]))
            if el.get("id"):
                a = self.sub(out, "a")
                a.set("id", self.prefixed_id(el))
            else:
                a = self.sub(out, "a")
                a.set("id", f"fntarg_{n}")
                a.set("href", f"#fnsrc_{n}")
            self.sub(a, "sup").text = el.get("callout") or str(n)
            self.add(out, "  ")
            nodes.append(self.add_all(out, self.children(el)))
        self.footnotes = []
        return nodes

    # ── Inline elements ───────────────────────────────────────────────────────

    def inline(self, el: etree._Element, tag: Optional[str]) -> List:
        if el.get(UNRESOLVED_KEY) and not (el.text or "").strip() and not len(el):
            return []
        extra = []
        if self.is_(el, "sw-d/systemoutput"):
            extra.append("sysout")
        if self.is_(el, "pr-d/kwd") and el.get("importance") == "default":
            extra.append("defkwd")
        nodes = self.wrap(tag, el, extra) if tag else self.children(el)
        href = el.get("href")
        if href and tag is not None:
            # keyref-resolved phrase: DITA-OT links the whole phrase.
            final = self.final_href(el, href)
            if final:
                return [self.add_all(self.anchor(el, final), nodes)]
        return nodes

    def tm(self, el: etree._Element) -> List:
        nodes = self.children(el)
        symbol = TRADEMARKS.get(el.get("tmtype") or "tm")
        mark = el.get("trademark") or _text(el)
        if symbol and mark not in self.trademarks_seen:
            self.trademarks_seen.add(mark)
            nodes.append(symbol)
        return nodes

    def boolean(self, el: etree._Element) -> List:
        out = self.element("span", el)
        out.text = f"boolean: {el.get('state') or ''}"
        return [out]

    def state(self, el: etree._Element) -> List:
        out = self.element("span", el, with_id=False)
        out.text = f"state: {el.get('name') or ''}={el.get('value') or ''}"
        return [out]

    def xref(self, el: etree._Element) -> List:
        href = el.get("href")
        desc = self.first_child(el, "topic/desc")
        content = self.children(el, skip=lambda c: c is desc)
        final = self.final_href(el, href) if href else None
        if final is None:
            if href and self.o.resolve_href is None:
                self.warn(f"Link '{href}' has an unsafe URL and was not linked")
            if not content and el.get(UNRESOLVED_KEY):
                return []
            span = self.element("span", el, with_id=False)
            return [self.add_all(span, content or ([href] if href else []))]
        a = self.anchor(el, final, ["xref"])
        if desc is not None and _text(desc):
            a.set("title", _text(desc))
        if not any(isinstance(n, str) and n.strip() or not isinstance(n, str) for n in content):
            content = [self.xref_text(el, href, final)]
        target = self.sub(a, "sup") if el.get("type") == "fn" else a
        self.add_all(target, content)
        return [a]

    def xref_text(self, el: etree._Element, href: str, final: str) -> str:
        if el.get("type") == "fn" and href.startswith("#"):
            _, _, fn_id = href[1:].partition("/")
            for fn, n in self.fn_numbers.items():
                if fn.get("id") == fn_id:
                    return fn.get("callout") or str(n)
        text = self.local_target_text(href)
        if text:
            return text
        if href.startswith("mailto:") and self.is_external(el):
            return href[len("mailto:"):]
        return final

    def menucascade(self, el: etree._Element) -> List:
        out = self.element("span", el)
        first = True
        for child in el:
            if not isinstance(child.tag, str):
                continue
            if self.is_(child, "ui-d/uicontrol"):
                if not first:
                    sep = self.sub(out, "abbr")
                    sep.set("title", "and then")
                    sep.text = " > "
                first = False
            self.add_all(out, self.render(child))
        return [out]

    def xml_markup(self, el: etree._Element) -> List:
        wrap = {
            "xml-d/xmlelement": ("<", ">"), "xml-d/xmlatt": ("@", ""),
            "xml-d/textentity": ("&", ";"), "xml-d/parameterentity": ("%", ";"),
            "xml-d/numcharref": ("&#", ";"), "xml-d/xmlpi": ("<?", "?>"),
            "xml-d/xmlnsname": ("", ""), "markup-d/markupname": ("<", ">"),
        }
        before, after = next((wrap[t] for t in reversed(_tokens(el)) if t in wrap), ("", ""))
        out = self.element("code", el, with_id=False)
        return [self.add_all(out, [before, *self.children(el), after])]

    def abbreviated_form(self, el: etree._Element) -> List:
        definition = self.o.keys.get((el.get("keyref") or "").split("/", 1)[0])
        if definition is None or not definition.text:
            self.warn(f"abbreviated-form '{el.get('keyref')}' has no key text and was not rendered")
            return []
        out = self.element("dfn", el, ["term"])
        out.text = definition.text
        final = self.final_href(el, definition.href) if definition.href else None
        return [self.add_all(self.anchor(el, final), [out])] if final else [out]

    def cmd(self, el: etree._Element) -> List:
        nodes = self.inline(el, "span")
        if not _text(el):
            nodes.append(etree.Element("br"))
        return nodes

    # ── Tables ────────────────────────────────────────────────────────────────

    def table(self, el: etree._Element) -> List:
        tgroups = [c for c in el if self.is_(c, "topic/tgroup")]
        if not any(len(b) for g in tgroups for b in g if self.is_(b, "topic/tbody")):
            return []
        extra = [f"frame-{el.get('frame')}"] if el.get("frame") else []
        if el.get("pgwide"):
            extra.append(f"table--pgwide-{el.get('pgwide')}")
        if el.get("scale"):
            extra.append(f"scale-{el.get('scale')}")
        out = self.element("table", el, extra)
        title = self.first_child(el, "topic/title")
        desc = self.first_child(el, "topic/desc")
        caption = self.sub(out, "caption")
        if title is not None:
            self.table_count += 1
            self.sub(caption, "span", "table--title-label").text = f"Table {self.table_count}. "
            caption.append(self.add_all(self.element("span", title), self.children(title)))
        if desc is not None:
            caption.append(self.add_all(self.element("span", desc, ["tabledesc"]), self.children(desc)))
        for group in tgroups:
            self.tgroup(group, out, el)
        return [out]

    def tgroup(self, group: etree._Element, out: etree._Element, table: etree._Element) -> None:
        colspecs = [c for c in group if self.is_(c, "topic/colspec")]
        columns: Dict[str, int] = {}
        widths: List[Optional[str]] = []
        for index, spec in enumerate(colspecs, start=1):
            number = int(spec.get("colnum")) if (spec.get("colnum") or "").isdigit() else index
            if spec.get("colname"):
                columns[spec.get("colname")] = number
            widths.append((spec.get("colwidth") or "").strip() or None)
        spans = {
            s.get("spanname"): (s.get("namest"), s.get("nameend"))
            for s in group if self.is_(s, "topic/spanspec") and s.get("spanname")
        }
        if colspecs:
            stars = [float(w[:-1] or 1) for w in widths if w and re.fullmatch(r"\s*[0-9.]*\*\s*", w)]
            total = sum(stars)
            colgroup = self.sub(out, "colgroup")
            for width in widths:
                col = self.sub(colgroup, "col")
                width = width or ""
                if re.fullmatch(r"[0-9.]*\*", width) and total:
                    col.set("width", f"{float(width[:-1] or 1) / total * 100:g}%")
                elif _to_px(width):
                    col.set("width", _to_px(width))
        align_by_col = {columns.get(s.get("colname"), i): s.get("align") for i, s in enumerate(colspecs, 1)}
        for section in group:
            if self.is_(section, "topic/thead") or self.is_(section, "topic/tbody"):
                head = self.is_(section, "topic/thead")
                sec = self.element("thead" if head else "tbody", section,
                                   [f"valign-{section.get('valign')}"] if section.get("valign") else [])
                occupied: Dict[int, int] = {}  # column → rows still covered by a rowspan
                for row in section:
                    if not self.is_(row, "topic/row"):
                        continue
                    tr = self.element("tr", row, [f"{a}-{row.get(a)}" for a in ("rowsep", "valign") if row.get(a)])
                    column = 1
                    for entry in row:
                        if not self.is_(entry, "topic/entry"):
                            continue
                        while occupied.get(column, 0) > 0:
                            column += 1
                        start, end = entry.get("namest"), entry.get("nameend")
                        if entry.get("spanname") in spans:
                            start, end = spans[entry.get("spanname")]
                        if start in columns:
                            column = columns[start]
                        elif entry.get("colname") in columns:
                            column = columns[entry.get("colname")]
                        colspan = columns[end] - column + 1 if end in columns and columns[end] >= column else 1
                        rowspan = int(entry.get("morerows")) + 1 if (entry.get("morerows") or "").isdigit() else 1
                        tr.append(self.entry(entry, head, table, column, colspan, rowspan,
                                             align_by_col.get(column) or group.get("align")))
                        for c in range(column, column + colspan):
                            occupied[c] = rowspan
                        column += colspan
                    occupied = {c: n - 1 for c, n in occupied.items() if n > 1}
                    sec.append(tr)
                out.append(sec)

    def entry(self, entry: etree._Element, head: bool, table: etree._Element, column: int,
              colspan: int, rowspan: int, inherited_align: Optional[str]) -> etree._Element:
        scope = entry.get("scope")
        row_header = scope in ("row", "rowgroup") or (table.get("rowheader") == "firstcol" and column == 1)
        tag = "th" if head or scope in ("col", "colgroup") or (row_header and not head) else "td"
        extra = []
        align = entry.get("align") or inherited_align
        if align:
            extra.append(f"align-{align}")
        if entry.get("valign"):
            extra.append(f"valign-{entry.get('valign')}")
        if entry.get("rotate") == "1":
            extra.append("rotate")
        cell = self.element(tag, entry, extra)
        if head or scope in ("col", "colgroup"):
            cell.set("scope", scope or "col")
        elif row_header:
            cell.set("scope", scope or "row")
        if colspan > 1:
            cell.set("colspan", str(colspan))
        if rowspan > 1:
            cell.set("rowspan", str(rowspan))
        return self.add_all(cell, self.children(entry))

    def simpletable(self, el: etree._Element, kind: str = "simpletable") -> List:
        rows = [c for c in el if self.is_(c, "topic/strow") or self.is_(c, "topic/sthead")]
        if not any(self.is_(r, "topic/strow") and len(r) for r in rows):
            return []
        extra = [f"{a}-{el.get(a)}" for a in ("frame", "expanse", "scale") if el.get(a)]
        out = self.element("table", el, extra)
        title = self.first_child(el, "topic/title")
        if title is not None:
            self.table_count += 1
            caption = self.sub(out, "caption")
            self.sub(caption, "span", "table--title-label").text = f"Table {self.table_count}. "
            self.add_all(caption, self.children(title))
        count = max((sum(1 for c in r if self.is_(c, "topic/stentry")) for r in rows), default=0)
        relative = (el.get("relcolwidth") or "").split()
        weights = []
        for index in range(count):
            raw = relative[index].rstrip("*") if index < len(relative) else "1"
            try:
                weights.append(float(raw or 1))
            except ValueError:
                weights.append(1.0)
        colgroup = self.sub(out, "colgroup")
        for weight in weights:
            self.sub(colgroup, "col").set("width", f"{weight / sum(weights) * 100:g}%")
        keycol = int(el.get("keycol")) if (el.get("keycol") or "").isdigit() else None
        thead = tbody = None
        for row in rows:
            head = self.is_(row, "topic/sthead")
            if head:
                thead = thead if thead is not None else self.sub(out, "thead")
                parent = thead
            else:
                tbody = tbody if tbody is not None else etree.Element("tbody")
                parent = tbody
            tr = self.element("tr", row)
            for index, cell in enumerate((c for c in row if self.is_(c, "topic/stentry")), start=1):
                is_th = head or index == keycol or cell.get("scope")
                td = self.element("th" if is_th else "td", cell)
                if head:
                    td.set("scope", "col")
                elif is_th:
                    td.set("scope", cell.get("scope") or "row")
                for name in ("colspan", "rowspan"):
                    if (cell.get(name) or "").isdigit():
                        td.set(name, cell.get(name))
                content = self.children(cell)
                if not _text(cell) and not len(cell) and cell.get("specentry"):
                    content = [cell.get("specentry")]
                tr.append(self.add_all(td, content))
            if len(tr):
                parent.append(tr)
        if tbody is not None:
            out.append(tbody)
        return self.spectitle(el) + [out]

    def properties(self, el: etree._Element) -> List:
        kinds = [("reference/proptype", "proptype", "Type"), ("reference/propvalue", "propvalue", "Value"),
                 ("reference/propdesc", "propdesc", "Description")]
        rows = [c for c in el if self.is_(c, "reference/property")]
        head = self.first_child(el, "reference/prophead")
        present = [
            k for k in kinds
            if any(self.first_child(r, k[0]) is not None for r in rows)
            or (head is not None and self.first_child(head, k[0] + "hd") is not None)
        ]
        if not rows or not present:
            return []
        extra = ["simpletablenoborder" if el.get("frame") == "none" else "simpletableborder"]
        out = self.element("table", el, extra)
        keycol = int(el.get("keycol")) if (el.get("keycol") or "").isdigit() else None
        thead = self.sub(out, "thead")
        tr = self.element("tr", head) if head is not None else etree.Element("tr", {"class": "sthead prophead"})
        for token, cls, label in present:
            authored = self.first_child(head, token + "hd") if head is not None else None
            th = self.element("th", authored) if authored is not None else etree.Element("th", {"class": f"stentry {cls}hd"})
            th.set("scope", "col")
            self.add_all(th, self.children(authored) if authored is not None else [label])
            tr.append(th)
        thead.append(tr)
        tbody = self.sub(out, "tbody")
        for row in rows:
            tr = self.element("tr", row)
            for index, (token, cls, _) in enumerate(present, start=1):
                cell = self.first_child(row, token)
                is_th = index == keycol
                td = self.element("th" if is_th else "td", cell) if cell is not None else \
                    etree.Element("th" if is_th else "td", {"class": f"stentry {cls}"})
                if is_th:
                    td.set("scope", "row")
                content = self.children(cell) if cell is not None else []
                if cell is not None and not _text(cell) and not len(cell) and cell.get("specentry"):
                    content = [cell.get("specentry")]
                tr.append(self.add_all(td, content))
            tbody.append(tr)
        return self.spectitle(el) + [out]

    def choicetable(self, el: etree._Element) -> List:
        rows = [c for c in el if self.is_(c, "task/chrow")]
        if not rows:
            return []
        out = self.element("table", el, ["choicetableborder"])
        keycol = int(el.get("keycol")) if (el.get("keycol") or "").isdigit() else 1
        head = self.first_child(el, "task/chhead")
        thead = self.sub(out, "thead")
        tr = self.element("tr", head) if head is not None else etree.Element("tr", {"class": "sthead chhead"})
        for token, cls, label in (("task/choptionhd", "choptionhd", "Option"), ("task/chdeschd", "chdeschd", "Description")):
            authored = self.first_child(head, token) if head is not None else None
            th = self.element("th", authored) if authored is not None else etree.Element("th", {"class": f"stentry {cls}"})
            th.set("scope", "col")
            tr.append(self.add_all(th, self.children(authored) if authored is not None else [label]))
        thead.append(tr)
        tbody = self.sub(out, "tbody")
        for row in rows:
            tr = self.element("tr", row)
            for index, token in enumerate(("task/choption", "task/chdesc"), start=1):
                cell = self.first_child(row, token)
                is_th = index == keycol
                td = self.element("th" if is_th else "td", cell) if cell is not None else etree.Element("td")
                if is_th:
                    td.set("scope", "row")
                tr.append(self.add_all(td, self.children(cell) if cell is not None else []))
            tbody.append(tr)
        return [out]

    # ── Task ──────────────────────────────────────────────────────────────────

    def steps(self, el: etree._Element) -> List:
        unordered = self.is_(el, "task/steps-unordered")
        section = etree.Element("section")
        if el.get("id"):
            section.set("id", self.prefixed_id(el))
        if self.o.task_labels:
            self.task_label(el, section)
        steps = [c for c in el if self.is_(c, "task/step")]
        if len(steps) == 1 and not unordered and not any(self.is_(c, "task/stepsection") for c in el):
            box = self.element("div", el, with_id=False)
            step = self.step(steps[0], single=True)[0]
            box.append(step)
            section.append(box)
            return [section]
        expand = any(
            self.is_(d, token) for s in steps for d in s
            for token in ("task/info", "task/stepxmp", "task/tutorialinfo", "task/stepresult")
        )
        current, count = None, 0
        for child in el:
            if self.is_(child, "task/stepsection"):
                current = None
                section.extend(self.wrap("div", child))
            elif self.is_(child, "task/step"):
                if current is None:
                    # The id is on the <section>; repeating it here would duplicate it.
                    current = self.element("ul" if unordered else "ol", el, with_id=False)
                    if count and not unordered:
                        current.set("start", str(count + 1))
                    section.append(current)
                count += 1
                current.extend(self.step(child, expand=expand))
            elif isinstance(child.tag, str):
                self.add_all(section, self.render(child))
        return [section]

    def step(self, el: etree._Element, single: bool = False, expand: bool = False) -> List:
        substep = self.is_(el, "task/substep")
        extra = [("substepexpand" if substep else "stepexpand")] if expand else []
        out = self.element("div" if single else "li", el, [*extra, *(["p"] if single else [])])
        importance = el.get("importance")
        if importance in ("optional", "required"):
            self.sub(out, "strong").text = f"{importance.capitalize()}: "
        return [self.add_all(out, self.children(el))]

    def substeps(self, el: etree._Element) -> List:
        subs = [c for c in el if self.is_(c, "task/substep")]
        if not subs:
            return []
        out = self.element("ol", el)
        if self.is_(el.getparent(), "task/step"):
            out.set("type", "a")
        expand = any(
            self.is_(d, token) for s in subs for d in s
            for token in ("task/info", "task/stepxmp", "task/tutorialinfo", "task/stepresult")
        )
        for child in el:
            if self.is_(child, "task/substep"):
                out.extend(self.step(child, expand=expand))
        return [out]

    def choices(self, el: etree._Element) -> List:
        return self.ul(el)

    # ── Hazard statements ────────────────────────────────────────────────────

    def hazardstatement(self, el: etree._Element) -> List:
        kind = el.get("type") or "caution"
        label = el.get("othertype") if kind == "other" and el.get("othertype") else NOTE_LABELS.get(kind, kind.capitalize())
        table = self.element("table", el, with_id=False)
        table.set("role", "presentation")
        head = self.sub(self.sub(table, "tr"), "th", f"hazardstatement--{kind}")
        symbols = [c for c in el if self.is_(c, "hazard-d/hazardsymbol")]
        head.set("colspan", "2" if symbols else "1")
        head.text = label
        row = self.sub(table, "tr")
        if symbols:
            cell = self.sub(row, "td", "hazardstatement--symbols")
            for symbol in symbols:
                self.add_all(cell, self.image(symbol))
        cell = self.sub(row, "td")
        for panel in (c for c in el if self.is_(c, "hazard-d/messagepanel")):
            box = self.sub(cell, "div", "messagepanel")
            for part in panel:
                if isinstance(part.tag, str):
                    name = _local_name(part)
                    self.add_all(self.sub(box, "div", name), self.children(part))
        return [table]

    # ── Syntax diagrams (DITA-OT "braces" rendering) ─────────────────────────

    def syntaxdiagram(self, el: etree._Element) -> List:
        out = self.element("div", el, ["fig"])
        title = self.first_child(el, "topic/title")
        if title is not None:
            self.add_all(self.sub(out, "h3", "title"), self.children(title))
        self.add_all(out, self.children(el, skip=lambda c: c is title))
        return [out]

    def synblk(self, el: etree._Element) -> List:
        title = self.first_child(el, "topic/title")
        out = self.element("div", el)
        if title is not None:
            self.add_all(self.sub(out, "h4", "title"), self.children(title))
        self.add_all(out, self.children(el, skip=lambda c: c is title))
        return [out]

    def group(self, el: etree._Element) -> List:
        choice = self.is_(el, "pr-d/groupchoice")
        parts: List = []
        first = True
        for child in el:
            if not isinstance(child.tag, str) or self.is_(child, "topic/title"):
                continue
            if choice and not first:
                parts.append(" | ")
            first = False
            parts.extend(self.render(child))
        if choice:
            parts = [" {", *parts, "} "]
        if el.get("importance") == "optional":
            parts = [" [", *parts, "] "]
        return parts

    def kwd(self, el: etree._Element) -> List:
        out = self.element("kbd", el, ["defkwd"] if el.get("importance") == "default" else [])
        self.add_all(self.sub(out, "b"), self.children(el))
        self.add(out, " ")
        return self.optional(el, [out])

    def syn_var(self, el: etree._Element) -> List:
        if not self.in_syntax(el):
            return self.inline(el, "span")
        return self.optional(el, self.wrap("var", el))

    def syn_kbd(self, el: etree._Element) -> List:
        if not self.in_syntax(el):
            return self.inline(el, "span")
        return self.optional(el, self.wrap("kbd", el))

    def in_syntax(self, el: etree._Element) -> bool:
        return any(self.is_(a, "pr-d/syntaxdiagram") for a in el.iterancestors())

    def optional(self, el: etree._Element, nodes: List) -> List:
        return [" [", *nodes, "] "] if el.get("importance") == "optional" else nodes

    def fragref(self, el: etree._Element) -> List:
        out = etree.Element("kbd")
        a = self.sub(out, "a")
        a.set("href", "#" + (el.get("href") or _text(el)).lstrip("#"))
        a.text = f"<{_text(el)}>"
        return [out]

    def imagemap(self, el: etree._Element) -> List:
        # <map>/<area> do not survive HTML sanitizers; show the image and its targets.
        out = self.element("div", el, ["fig"])
        image = self.first_child(el, "topic/image")
        if image is not None:
            self.add_all(out, self.image(image))
        areas = [a for a in el if self.is_(a, "ut-d/area")]
        if areas:
            ul = self.sub(out, "ul", "ul imagemap-areas")
            for area in areas:
                xref = next((c for c in area if self.is_(c, "topic/xref")), None)
                if xref is not None:
                    self.add_all(self.sub(ul, "li", "li"), self.render(xref))
        return [out]


HANDLERS: Dict[str, Callable[[_Render, etree._Element], List]] = {
    "topic/topic": _Render.topic,
    "topic/title": _Render.title,
    "topic/shortdesc": _Render.shortdesc,
    "topic/abstract": _Render.abstract,
    "topic/body": _Render.div,
    "topic/bodydiv": _Render.div,
    "topic/sectiondiv": _Render.div,
    "topic/div": _Render.div,
    "topic/section": _Render.section,
    "topic/example": _Render.section,
    "topic/related-links": _Render.related_links,
    "topic/link": _Render.link,
    "topic/p": _Render.p,
    "topic/lq": _Render.lq,
    "topic/note": _Render.note,
    "topic/pre": _Render.pre,
    "pr-d/codeblock": _Render.codeblock,
    "topic/lines": _Render.lines,
    "topic/fig": _Render.fig,
    "topic/figgroup": _Render.figgroup,
    "topic/image": _Render.image,
    "topic/ul": _Render.ul,
    "topic/ol": _Render.ol,
    "topic/sl": _Render.sl,
    "topic/li": _Render.li,
    "topic/sli": _Render.sli,
    "topic/itemgroup": _Render.itemgroup,
    "topic/dl": _Render.dl,
    "topic/dlentry": _Render.dlentry,
    "topic/dlhead": _Render.dlhead,
    "topic/draft-comment": _Render.draft_comment,
    "topic/required-cleanup": _Render.required_cleanup,
    "topic/fn": _Render.fn,
    "topic/tm": _Render.tm,
    "topic/boolean": _Render.boolean,
    "topic/state": _Render.state,
    "topic/xref": _Render.xref,
    "topic/table": _Render.table,
    "topic/simpletable": _Render.simpletable,
    "reference/properties": _Render.properties,
    "task/choicetable": _Render.choicetable,
    "task/steps": _Render.steps,
    "task/steps-unordered": _Render.steps,
    "task/step": _Render.step,
    "task/substeps": _Render.substeps,
    "task/substep": _Render.step,
    "task/choices": _Render.choices,
    "task/cmd": _Render.cmd,
    "ui-d/menucascade": _Render.menucascade,
    "hazard-d/hazardstatement": _Render.hazardstatement,
    "abbrev-d/abbreviated-form": _Render.abbreviated_form,
    "xml-d/xmlelement": _Render.xml_markup,
    "xml-d/xmlatt": _Render.xml_markup,
    "xml-d/textentity": _Render.xml_markup,
    "xml-d/parameterentity": _Render.xml_markup,
    "xml-d/numcharref": _Render.xml_markup,
    "xml-d/xmlpi": _Render.xml_markup,
    "xml-d/xmlnsname": _Render.xml_markup,
    "markup-d/markupname": _Render.xml_markup,
    "pr-d/syntaxdiagram": _Render.syntaxdiagram,
    "pr-d/synblk": _Render.synblk,
    "pr-d/fragment": _Render.synblk,
    "pr-d/groupseq": _Render.group,
    "pr-d/groupchoice": _Render.group,
    "pr-d/groupcomp": _Render.group,
    "pr-d/kwd": _Render.kwd,
    "pr-d/var": _Render.syn_var,
    "pr-d/oper": _Render.syn_kbd,
    "pr-d/delim": _Render.syn_kbd,
    "pr-d/sep": _Render.syn_kbd,
    "pr-d/fragref": _Render.fragref,
    "ut-d/imagemap": _Render.imagemap,
}
