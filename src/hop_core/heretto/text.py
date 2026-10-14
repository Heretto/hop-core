"""DITA to readable text, for handing Heretto content to a model.

Markdown-flavoured plain text: headings, paragraphs, lists, definition and
glossary entries, tables as pipe rows, code blocks. Markup that carries no
meaning for a reader — prolog metadata, index terms, draft comments — is
dropped. Pure standard library, so it works without the ``dita`` extra.

This is a reading aid, not a renderer: conrefs and keyrefs are not resolved
(the referencing element keeps whatever text it has), and output formatting
is deliberately simple.
"""

import html.entities
import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple

# Elements whose content is never shown to a reader.
_SKIP = {
    "prolog", "metadata", "titlealts", "navtitle", "searchtitle", "indexterm",
    "draft-comment", "required-cleanup", "data", "data-about", "foreign",
    "unknown", "object", "image", "audience", "keywords", "resourceid",
}
# Block containers that just hold other blocks.
_CONTAINERS = {
    "body", "conbody", "taskbody", "refbody", "troublebody", "glossBody",
    "bodydiv", "sectiondiv", "div", "context", "result", "postreq", "prereq",
    "steps-informal", "example", "fig", "lq", "abstract", "related-links",
    "info", "stepresult", "stepxmp", "tutorialinfo", "itemgroup", "dd", "li",
    "entry", "stentry", "glossdef", "glossUsage", "glossScopeNote", "linkinfo",
}
_PARAGRAPHS = {"p", "shortdesc", "cmd", "linktext", "desc", "stepsection", "glossSurfaceForm"}
_LISTS = {"ul": "-", "ol": "1.", "sl": "-", "steps": "1.", "steps-unordered": "-", "substeps": "1.", "choices": "-"}
_LIST_ITEMS = {"li", "sli", "step", "substep", "choice"}
_NOTE_LABELS = {"note": "Note", "hazardstatement": "Warning"}
_CODE = {"codeblock", "pre", "msgblock", "screen", "lines"}
_XML_ENTITIES = {"amp", "lt", "gt", "quot", "apos"}
_ENTITY = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")
_SPACE = re.compile(r"\s+")


def _local(tag) -> str:
    if not isinstance(tag, str):
        return ""  # comments and processing instructions
    return tag.split("}", 1)[1] if "}" in tag else tag


def _numeric_entities(raw: str) -> str:
    """DITA files lean on DTD-defined entities (``&nbsp;``) that a parser
    without the DTD rejects; swap the HTML ones for numeric references."""
    def swap(m: "re.Match[str]") -> str:
        name = m.group(1)
        if name in _XML_ENTITIES:
            return m.group(0)
        codepoint = html.entities.name2codepoint.get(name)
        return f"&#{codepoint};" if codepoint else m.group(0)
    return _ENTITY.sub(swap, raw)


class _Writer:
    def __init__(self, base_level: int):
        self.blocks: List[str] = []
        self.base_level = base_level

    # ── inline ────────────────────────────────────────────────────────────

    def inline(self, el: ET.Element) -> str:
        parts: List[str] = [el.text or ""]
        for child in el:
            name = _local(child.tag)
            if name and name not in _SKIP:
                inner = self.inline(child).strip()
                if name in ("b", "uicontrol", "term", "glossterm"):
                    inner = f"**{inner}**" if inner else inner
                elif name in ("i", "cite"):
                    inner = f"*{inner}*" if inner else inner
                elif name in ("codeph", "filepath", "cmdname", "varname", "apiname", "option", "parmname"):
                    inner = f"`{inner}`" if inner else inner
                elif name == "xref" and not inner:
                    inner = child.get("href") or ""
                parts.append(inner)
            parts.append(child.tail or "")
        return _SPACE.sub(" ", "".join(parts))

    # ── blocks ────────────────────────────────────────────────────────────

    def add(self, text: str) -> None:
        text = text.strip()
        if text:
            self.blocks.append(text)

    def heading(self, level: int, text: str) -> None:
        if text.strip():
            self.add("#" * max(1, min(level, 6)) + " " + text.strip())

    def topic(self, el: ET.Element, level: int) -> None:
        for child in el:
            name = _local(child.tag)
            if name == "title":
                self.heading(level, self.inline(child))
            elif name in ("glossterm",):
                self.heading(level, self.inline(child))
            elif _is_topic(child):
                self.topic(child, level + 1)
            else:
                self.block(child, level + 1)

    def block(self, el: ET.Element, section_level: int, indent: str = "") -> None:
        name = _local(el.tag)
        if not name or name in _SKIP:
            return
        if name in ("section", "refsyn"):
            for child in el:
                if _local(child.tag) == "title":
                    self.heading(section_level, self.inline(child))
                else:
                    self.block(child, section_level + 1, indent)
            return
        if name == "title":
            self.heading(section_level, self.inline(el))
            return
        if name in _PARAGRAPHS:
            self.add(indent + self.inline(el))
            return
        if name in _NOTE_LABELS:
            label = el.get("type") or _NOTE_LABELS[name]
            body = self._collect(el, section_level)
            self.add(f"{indent}> **{label.capitalize()}:** {body}")
            return
        if name in _CODE:
            text = "".join(el.itertext()).strip("\n")
            self.add(f"```\n{text}\n```")
            return
        if name in _LISTS:
            marker = _LISTS[name]
            for item in el:
                if _local(item.tag) in _LIST_ITEMS:
                    self.add(f"{indent}{marker} {self._collect(item, section_level)}")
            return
        if name in ("dl", "parml"):
            for entry in el:
                terms = [self.inline(t).strip() for t in entry if _local(t.tag) in ("dt", "pt")]
                defs = [self._collect(d, section_level) for d in entry if _local(d.tag) in ("dd", "pd")]
                if terms:
                    self.add(f"{indent}- **{' / '.join(terms)}**: {' '.join(defs)}")
            return
        if name in ("table", "simpletable", "properties", "choicetable"):
            self.table(el)
            return
        if name in ("glossentry",):
            self.topic(el, section_level)
            return
        if name in _CONTAINERS or len(el):
            if (el.text or "").strip():
                self.add(indent + self.inline(el))
                return
            for child in el:
                self.block(child, section_level, indent)
            return
        self.add(indent + self.inline(el))

    def _collect(self, el: ET.Element, section_level: int) -> str:
        """Everything inside ``el`` flattened onto one line (list items, notes)."""
        nested = _Writer(self.base_level)
        if (el.text or "").strip() and not any(_local(c.tag) in _PARAGRAPHS | set(_LISTS) for c in el):
            return self.inline(el).strip()
        for child in el:
            nested.block(child, section_level, "")
        lead = (el.text or "").strip()
        return " ".join(filter(None, [lead] + nested.blocks))

    def table(self, el: ET.Element) -> None:
        title = next((c for c in el if _local(c.tag) == "title"), None)
        if title is not None:
            self.add(f"**{self.inline(title).strip()}**")
        rows = []
        for row in el.iter():
            if _local(row.tag) in ("row", "strow", "sthead", "prophead", "property", "chrow", "chhead"):
                cells = [self._collect(c, 6).replace("|", "\\|") for c in row]
                if any(cells):
                    rows.append("| " + " | ".join(cells) + " |")
        if rows:
            self.add("\n".join(rows))


def _is_topic(el: ET.Element) -> bool:
    """Any topic specialization: it has an id-bearing title-first structure."""
    name = _local(el.tag)
    return name in {
        "topic", "concept", "task", "reference", "troubleshooting", "glossentry",
        "glossgroup", "learningContent", "learningOverview", "learningSummary",
    } or (len(el) > 0 and _local(el[0].tag) == "title" and el.get("id") is not None
          and name not in ("section", "table", "fig", "example"))


def dita_to_text(raw: bytes | str, heading_level: int = 1) -> Tuple[Optional[str], str]:
    """Return ``(title, text)`` for one DITA document.

    ``heading_level`` is the Markdown level of the topic's own title, so a
    map can nest its topics under its own heading.
    """
    source = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    try:
        root = ET.fromstring(_numeric_entities(source))
    except ET.ParseError:
        # Not well-formed: fall back to the bare text rather than nothing.
        text = _SPACE.sub(" ", re.sub(r"<[^>]+>", " ", source)).strip()
        return None, text

    title_el = next((c for c in root if _local(c.tag) in ("title", "glossterm")), None)
    title = _SPACE.sub(" ", "".join(title_el.itertext())).strip() if title_el is not None else None

    writer = _Writer(heading_level)
    if _is_topic(root):
        writer.topic(root, heading_level)
    else:
        writer.block(root, heading_level)
    return title, "\n\n".join(writer.blocks)
