"""
Tests for DitaRenderer: DITA topic → HTML5, modeled on DITA-OT's HTML5 output.

Covers:
- DITA-OT output conventions: @class ancestry classes, {topicid}__{id} ids,
  heading levels, generated labels, figure/table numbering, footnotes
- Topic types (topic, concept, task, reference, glossentry) and nesting
- Tables (colspec widths, spans), simpletable, properties, choicetable
- Preprocessing: conref (same file and via loader), keyref, filtering
- Safety: unsafe URLs, markup in text, namespaced/foreign content
- The POST /dita/render route
"""

from pathlib import Path

import pytest
from lxml import html as lxml_html

from hop_core.dita import (
    DitaParseError,
    DitaRenderer,
    KeyDefinition,
    exclusions_from_ditaval,
    keys_from_map,
    render_dita,
)

FIXTURES = Path(__file__).parent / "fixtures" / "dita"


def parse(result_html: str):
    """Parse a rendered fragment for structural assertions."""
    return lxml_html.fragment_fromstring(result_html, create_parent="div")


def one(tree, xpath: str):
    found = tree.xpath(xpath)
    assert len(found) == 1, f"{xpath!r} matched {len(found)} nodes"
    return found[0]


def topic(body: str, *, root: str = "topic", body_tag: str = "body", extra: str = "", attrs: str = "") -> str:
    return (
        f'<{root} id="t1"{attrs}><title>Title</title>{extra}'
        f"<{body_tag}>{body}</{body_tag}></{root}>"
    )


# ---------------------------------------------------------------------------
# Structure and DITA-OT conventions
# ---------------------------------------------------------------------------

class TestStructure:
    def test_every_valid_fixture_renders_without_warnings(self):
        for path in sorted((FIXTURES / "valid").glob("*.dita")):
            result = render_dita(path.read_text(encoding="utf-8"))
            assert result.html.startswith("<article"), path.name
            assert result.title, path.name
            assert result.warnings == [], (path.name, result.warnings)

    def test_kitchen_sink_fixture(self):
        # Mixed content across domains, with keys and filtering — only the
        # deliberately unsafe link should produce a warning.
        result = DitaRenderer(
            exclude={"audience": ["expert"]},
            keys={"product": KeyDefinition(text="AcmeCLI", href="https://acme.test", scope="external")},
        ).render((FIXTURES / "render" / "kitchen_sink.dita").read_text(encoding="utf-8"))
        tree = parse(result.html)
        assert result.warnings == ["Link 'javascript:alert(1)' has an unsafe URL and was not linked"]
        assert "Experts only" not in result.html and "hide me" not in result.html
        assert one(tree, "//h1").text_content() == "Configuring Acme\u00ae Server"
        assert len(tree.xpath("//p[.='Reused paragraph with bold.']")) == 2
        assert one(tree, "//article[@id='nested']").get("class") == "topic concept nested1"

    def test_root_topic_article_title_and_metadata(self):
        result = render_dita(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">'
            '<concept id="c1" xml:lang="de-DE"><title>Über <ph>uns</ph></title>'
            "<shortdesc>Kurz  gesagt.</shortdesc><conbody><p>Text</p></conbody></concept>"
        )
        tree = parse(result.html)
        article = one(tree, "article")
        assert article.get("class") == "topic concept nested0"
        assert article.get("id") == "c1"
        assert article.get("lang") == "de-DE"
        assert article.get("aria-labelledby") == "ariaid-title1"
        h1 = one(tree, "//h1")
        assert h1.get("class") == "title topictitle1" and h1.get("id") == "ariaid-title1"
        assert h1.text_content() == "Über uns"
        assert (result.title, result.shortdesc, result.topic_id, result.topic_type, result.lang) == (
            "Über uns", "Kurz gesagt.", "c1", "concept", "de-DE",
        )

    def test_shortdesc_moves_into_body_like_dita_ot(self):
        tree = parse(render_dita(topic("<p>Body</p>", extra="<shortdesc>Short</shortdesc>")).html)
        body = one(tree, "//div[@class='body']")
        assert body[0].tag == "p" and body[0].get("class") == "shortdesc"

    def test_class_is_specialization_ancestry_plus_outputclass(self):
        tree = parse(render_dita(topic(
            '<p>Click <uicontrol outputclass="big">OK</uicontrol> in <wintitle>Setup</wintitle>.</p>'
        )).html)
        assert one(tree, "//span[.='OK']").get("class") == "ph uicontrol big"
        assert one(tree, "//span[.='Setup']").get("class") == "keyword wintitle"

    def test_explicit_class_attribute_wins_over_dtd_default(self):
        # Preprocessed or specialized content carries its own @class.
        tree = parse(render_dita(topic('<p>A <mything class="+ topic/ph acme-d/mything ">x</mything></p>')).html)
        assert one(tree, "//span[.='x']").get("class") == "ph mything"

    def test_element_ids_are_prefixed_with_topic_id(self):
        tree = parse(render_dita(topic('<p id="p1">A</p><section id="s1"><p>B</p></section>')).html)
        assert tree.xpath("//p[@id='t1__p1']")
        assert tree.xpath("//section[@id='t1__s1']")

    def test_nested_topics_and_heading_levels(self):
        result = render_dita(
            '<topic id="a"><title>A</title><body><section><title>S</title><p>x</p></section></body>'
            '<topic id="b"><title>B</title><body><p>y</p></body>'
            '<topic id="c"><title>C</title></topic></topic></topic>'
        )
        tree = parse(result.html)
        assert one(tree, "//h2[@class='title sectiontitle']").text == "S"
        b = one(tree, "//article[@id='b']")
        assert b.get("class") == "topic nested1" and b.get("aria-labelledby") == "ariaid-title2"
        assert one(tree, "//h2[@class='title topictitle2']").text == "B"
        assert one(tree, "//h3[@class='title topictitle3']").text == "C"

    def test_heading_offset_pushes_levels_down(self):
        tree = parse(DitaRenderer(heading_offset=1).render(
            topic("<section><title>S</title></section>")
        ).html)
        assert one(tree, "//h2").get("class") == "title topictitle1"
        assert one(tree, "//h3").text == "S"

    def test_dita_container_renders_each_topic(self):
        result = render_dita(
            '<dita><topic id="a"><title>A</title></topic><concept id="b"><title>B</title></concept></dita>'
        )
        tree = parse(result.html)
        assert [a.get("class") for a in tree.xpath("article")] == ["topic nested0", "topic concept nested0"]
        assert result.title == "A"

    def test_bare_element_renders_as_fragment(self):
        result = render_dita("<section><title>Only</title><p>x</p></section>")
        assert parse(result.html).xpath("section/h1[.='Only']")
        assert result.topic_type == "section"

    def test_prolog_and_metadata_are_not_rendered(self):
        result = render_dita(topic("<p>Visible</p>", extra="<prolog><author>Secret</author></prolog>"))
        assert "Secret" not in result.html

    def test_map_is_rejected(self):
        with pytest.raises(DitaParseError, match="map"):
            render_dita('<map><topicref href="a.dita"/></map>')

    def test_malformed_xml_raises_parse_error(self):
        malformed = (FIXTURES / "invalid" / "topic_malformed_xml.dita").read_text()
        with pytest.raises(DitaParseError):
            render_dita(malformed)

    def test_accepts_bytes_and_non_utf8_declarations(self):
        xml = '<?xml version="1.0" encoding="ISO-8859-1"?><topic id="t"><title>Café</title></topic>'
        assert render_dita(xml).title == "Café"
        assert render_dita(xml.encode("iso-8859-1")).title == "Café"

    def test_unknown_element_warns_and_keeps_text(self):
        result = render_dita(topic("<p>A <blink>B</blink></p>"))
        assert one(parse(result.html), "//span[@class='undefined_element']").text == "B"
        assert any("blink" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Block and inline elements
# ---------------------------------------------------------------------------

class TestBlocks:
    @pytest.mark.parametrize("attrs,cls,label", [
        ("", "note note_note", "Note:"),
        (' type="tip"', "note tip note_tip", "Tip:"),
        (' type="caution"', "note caution note_caution", "CAUTION:"),
        (' type="danger"', "note danger note_danger", "DANGER:"),
        (' type="other" othertype="Heads up"', "note note_note", "Heads up:"),
    ])
    def test_notes(self, attrs, cls, label):
        tree = parse(render_dita(topic(f"<note{attrs}>Careful</note>")).html)
        note = one(tree, "//div[span[@class='note__title']]")
        assert note.get("class") == cls
        assert one(note, "span").text == label
        assert one(note, "div[@class='note__body']").text == "Careful"

    def test_p_with_block_content_becomes_div(self):
        tree = parse(render_dita(topic("<p>Intro<ul><li>x</li></ul></p>")).html)
        assert tree.xpath("//div[@class='p']/ul")

    def test_lists(self):
        tree = parse(render_dita(topic(
            "<ol><li>a<ol><li>b<ol><li>c</li></ol></li></ol></li></ol>"
            "<sl><sli>s</sli></sl><ul compact='yes'><li>u</li></ul><ul/>"
        )).html)
        assert [ol.get("type") for ol in tree.xpath("//ol")] == [None, "a", "i"]
        assert one(tree, "//ul[li[.='s']]").get("class") == "sl simple"
        assert one(tree, "//ul[li[.='u']]").get("class") == "ul compact"
        assert len(tree.xpath("//ul")) == 2  # the empty list is dropped

    def test_definition_list(self):
        tree = parse(render_dita(topic(
            "<dl><dlhead><dthd>Term</dthd><ddhd>Meaning</ddhd></dlhead>"
            "<dlentry id='e1'><dt>API</dt><dd>Interface</dd></dlentry></dl>"
        )).html)
        assert one(tree, "//dt[@class='dthd']/strong").text == "Term"
        dt = one(tree, "//dt[@class='dt dlterm']")
        assert dt.text == "API" and dt.get("id") == "t1__e1"
        assert one(tree, "//dd[@class='dd']").text == "Interface"

    def test_codeblock_keeps_whitespace_and_language_class(self):
        tree = parse(render_dita(topic(
            '<codeblock outputclass="language-python">def f():\n    return 1</codeblock>'
        )).html)
        pre = one(tree, "//pre")
        assert pre.get("class") == "pre codeblock language-python"
        assert one(pre, "code").text == "def f():\n    return 1"

    def test_lines_become_line_breaks(self):
        tree = parse(render_dita(topic("<lines>one\n  two\nthree</lines>")).html)
        lines = one(tree, "//p[@class='lines']")
        assert len(lines.findall("br")) == 2
        assert lines.text_content() == "one  twothree"

    def test_figure_with_numbered_caption(self):
        tree = parse(render_dita(topic(
            '<fig frame="all"><title>First</title><desc>About it</desc><image href="a.png"/></fig>'
            "<fig><title>Second</title></fig>"
        )).html)
        figures = tree.xpath("//figure")
        assert figures[0].get("class") == "fig figborder"
        assert figures[1].get("class") == "fig fignone"
        caption = one(figures[0], "figcaption")
        assert caption.text_content() == "Figure 1. First. About it"
        assert one(figures[1], ".//span[@class='fig--title-label']").text == "Figure 2. "

    def test_image_attributes(self):
        tree = parse(render_dita(topic(
            '<p><image href="i.png" width="1in" height="30"><alt>Alt text</alt></image>'
            '<image href="j.png" placement="break" align="center" alt="J"/></p>'
        )).html)
        img = one(tree, "//img[@src='i.png']")
        assert (img.get("class"), img.get("width"), img.get("height"), img.get("alt")) == (
            "image", "96", "30", "Alt text",
        )
        assert one(tree, "//div[@class='imagecenter']/img").get("class") == "image imagecenter"

    def test_draft_content_hidden_unless_requested(self):
        xml = topic("<p>A<draft-comment author='pat'>fix</draft-comment></p>")
        assert "fix" not in render_dita(xml).html
        shown = parse(DitaRenderer(show_draft=True).render(xml).html)
        box = one(shown, "//div[@class='draft-comment']")
        assert box.text_content().startswith("Draft comment: pat")

    def test_footnotes_are_numbered_and_collected_as_endnotes(self):
        tree = parse(render_dita(
            '<topic id="t"><title>T</title><body><p>A<fn>First</fn> B<fn callout="*">Second</fn></p></body>'
            '<topic id="n"><title>N</title><body><p>C<fn>Third</fn></p></body></topic></topic>'
        ).html)
        callouts = tree.xpath("//a[starts-with(@href, '#fntarg_')]")
        assert [(a.get("id"), a.text_content()) for a in callouts] == [
            ("fnsrc_1", "1"), ("fnsrc_2", "*"), ("fnsrc_3", "3"),
        ]
        notes = tree.xpath("/div/article/div[@class='fn']")  # after nested topics, in the root article
        assert [n.text_content() for n in notes] == ["1  First", "*  Second", "3  Third"]

    def test_xref_forms(self):
        result = render_dita(
            '<topic id="t"><title>T</title><body>'
            '<section id="s"><title>Setup</title></section>'
            '<p><xref href="#t/s"/> <xref href="guide.dita#g/part">Guide</xref> '
            '<xref href="https://x.test" scope="external">X</xref> <xref>plain</xref> '
            '<xref href="mailto:a@b.test" scope="external"/></p></body></topic>'
        )
        tree = parse(result.html)
        local = one(tree, "//a[@href='#t__s']")
        assert (local.get("class"), local.text) == ("xref", "Setup")
        assert one(tree, "//a[.='Guide']").get("href") == "guide.html#g__part"
        external = one(tree, "//a[.='X']")
        assert (external.get("target"), external.get("rel")) == ("_blank", "external noopener")
        assert one(tree, "//span[@class='xref']").text == "plain"
        assert one(tree, "//a[starts-with(@href, 'mailto:')]").text == "a@b.test"

    def test_menucascade_and_domain_phrases(self):
        tree = parse(render_dita(topic(
            "<p><menucascade><uicontrol>File</uicontrol> <uicontrol>Save</uicontrol></menucascade>"
            " <b>b</b><i>i</i><codeph>c</codeph><userinput>u</userinput><varname>v</varname>"
            " <xmlelement>el</xmlelement><xmlatt>at</xmlatt><term>t</term><q>q</q></p>"
        )).html)
        cascade = one(tree, "//span[@class='ph menucascade']")
        assert cascade.text_content() == "File > Save"
        assert one(cascade, "abbr").get("title") == "and then"
        for xpath in ("//strong[@class='ph b']", "//em[@class='ph i']", "//code[@class='ph codeph']",
                      "//kbd[@class='ph userinput']", "//var[@class='keyword varname']",
                      "//dfn[@class='term']", "//q[@class='q']"):
            one(tree, xpath)
        assert one(tree, "//code[@class='keyword markupname xmlelement']").text == "<el>"
        assert one(tree, "//code[@class='keyword markupname xmlatt']").text == "@at"

    def test_trademark_symbol_on_first_use(self):
        html = render_dita(topic('<p><tm trademark="Acme" tmtype="reg">Acme</tm> and <tm trademark="Acme" tmtype="reg">Acme</tm></p>')).html
        assert html.count("®") == 1

    def test_related_links_grouped_by_type(self):
        tree = parse(render_dita(
            '<topic id="t"><title>T</title><related-links>'
            '<link href="c.dita" type="concept"><linktext>About</linktext></link>'
            '<link href="t.dita" type="task"><linktext>Do</linktext></link>'
            '<link href="https://x.test" scope="external" format="html"/>'
            "</related-links></topic>"
        ).html)
        nav = one(tree, "//nav[@class='related-links']")
        groups = [(g.get("class"), g.findtext("strong")) for g in nav.xpath("div")]
        assert groups == [
            ("linklist relconcepts", "Related concepts"),
            ("linklist reltasks", "Related tasks"),
            ("linklist relinfo", "Related information"),
        ]
        assert one(nav, ".//a[.='About']").get("href") == "c.html"


class TestTopicTypes:
    def test_task_steps(self):
        tree = parse(render_dita(topic(
            "<prereq>Before</prereq><steps>"
            "<step importance='optional'><cmd>One</cmd><info>More</info>"
            "<substeps><substep><cmd>1a</cmd></substep></substeps></step>"
            "<stepsection>Then</stepsection><step><cmd>Two</cmd></step></steps><result>Done</result>",
            root="task", body_tag="taskbody",
        )).html)
        assert one(tree, "//section[@class='section prereq']").text == "Before"
        lists = tree.xpath("//ol[contains(concat(' ', @class, ' '), ' steps ')]")
        assert [ol.get("start") for ol in lists] == [None, "2"]
        first = one(lists[0], "li")
        assert first.get("class") == "li step stepexpand"
        assert one(first, "strong").text == "Optional: "
        assert one(first, "span[@class='ph cmd']").text == "One"
        assert one(first, "div[@class='itemgroup info']").text == "More"
        assert one(first, "ol").get("class") == "ol substeps"
        assert one(tree, "//div[@class='li stepsection']").text == "Then"

    def test_single_step_is_not_a_numbered_list(self):
        tree = parse(render_dita(topic("<steps><step><cmd>Only</cmd></step></steps>",
                                       root="task", body_tag="taskbody")).html)
        assert not tree.xpath("//ol")
        assert one(tree, "//div[@class='ol steps']/div").get("class") == "li step p"

    def test_task_labels_are_opt_in(self):
        xml = topic("<prereq>x</prereq><steps><step><cmd>c</cmd></step></steps>",
                    root="task", body_tag="taskbody")
        assert "Before you begin" not in render_dita(xml).html
        tree = parse(DitaRenderer(task_labels=True).render(xml).html)
        labels = [h.text for h in tree.xpath("//div[@class='tasklabel']/*")]
        assert labels == ["Before you begin", "Procedure"]
        assert all(h.tag == "h2" for h in tree.xpath("//div[@class='tasklabel']/*"))

    def test_choicetable_default_headers(self):
        tree = parse(render_dita(topic(
            "<steps><step><cmd>c</cmd><choicetable><chrow><choption>A</choption>"
            "<chdesc>Desc</chdesc></chrow></choicetable></step><step><cmd>d</cmd></step></steps>",
            root="task", body_tag="taskbody",
        )).html)
        table = one(tree, "//table")
        assert table.get("class") == "simpletable choicetable choicetableborder"
        assert [th.text for th in table.xpath("thead/tr/th")] == ["Option", "Description"]
        assert one(table, "tbody/tr/th[@scope='row']").text == "A"

    def test_reference_properties(self):
        tree = parse(render_dita(topic(
            "<properties><property><proptype>int</proptype><propvalue>8080</propvalue>"
            "<propdesc>Port</propdesc></property></properties>",
            root="reference", body_tag="refbody",
        )).html)
        table = one(tree, "//table")
        assert "properties" in table.get("class")
        assert [th.text for th in table.xpath("thead/tr/th")] == ["Type", "Value", "Description"]
        assert [td.text for td in table.xpath("tbody/tr/td")] == ["int", "8080", "Port"]

    def test_glossentry(self):
        result = render_dita(
            '<glossentry id="g"><glossterm>API</glossterm><glossdef>An interface.</glossdef></glossentry>'
        )
        tree = parse(result.html)
        assert one(tree, "article").get("class") == "topic concept glossentry nested0"
        assert one(tree, "//h1").text == "API"
        assert one(tree, "//div[@class='abstract glossdef']").text == "An interface."
        assert result.title == "API"

    def test_hazardstatement(self):
        tree = parse(render_dita(topic(
            '<hazardstatement type="warning"><messagepanel><typeofhazard>Hot</typeofhazard>'
            "<howtoavoid>Wait.</howtoavoid></messagepanel></hazardstatement>"
        )).html)
        table = one(tree, "//table")
        assert table.get("class") == "note hazardstatement"
        assert one(table, ".//th").get("class") == "hazardstatement--warning"
        assert one(table, ".//th").text == "Warning"
        assert one(table, ".//div[@class='typeofhazard']").text == "Hot"


class TestTables:
    def test_cals_table_widths_spans_and_caption(self):
        tree = parse(render_dita(topic(
            '<table frame="all" pgwide="1"><title>Ports</title><desc>All of them</desc>'
            '<tgroup cols="3"><colspec colname="a" colwidth="1*"/><colspec colname="b" colwidth="3*"/>'
            '<colspec colname="c" colwidth="50pt"/>'
            "<thead><row><entry>H1</entry><entry>H2</entry><entry>H3</entry></row></thead>"
            '<tbody><row><entry morerows="1">A</entry><entry namest="b" nameend="c" align="center">BC</entry></row>'
            "<row><entry>B2</entry><entry>C2</entry></row></tbody></tgroup></table>"
        )).html)
        table = one(tree, "//table")
        assert table.get("class") == "table frame-all table--pgwide-1"
        caption = one(table, "caption")
        assert caption.text_content() == "Table 1. PortsAll of them"
        assert [c.get("width") for c in table.xpath("colgroup/col")] == ["25%", "75%", "67"]
        assert [(th.text, th.get("scope")) for th in table.xpath("thead/tr/th")] == [
            ("H1", "col"), ("H2", "col"), ("H3", "col"),
        ]
        a = one(table, ".//td[.='A']")
        assert a.get("rowspan") == "2"
        bc = one(table, ".//td[.='BC']")
        assert (bc.get("colspan"), bc.get("class")) == ("2", "entry align-center")

    def test_rowheader_firstcol(self):
        tree = parse(render_dita(topic(
            '<table rowheader="firstcol"><tgroup cols="2"><tbody><row><entry>K</entry><entry>V</entry>'
            "</row></tbody></tgroup></table>"
        )).html)
        assert one(tree, "//th[@scope='row']").text == "K"

    def test_simpletable(self):
        tree = parse(render_dita(topic(
            '<simpletable relcolwidth="1* 3*" keycol="1"><sthead><stentry>K</stentry><stentry>V</stentry></sthead>'
            '<strow><stentry>a</stentry><stentry specentry="(none)"/></strow></simpletable>'
        )).html)
        table = one(tree, "//table")
        assert table.get("class") == "simpletable"
        assert [c.get("width") for c in table.xpath("colgroup/col")] == ["25%", "75%"]
        assert one(table, "tbody/tr/th").text == "a"
        assert one(table, "tbody/tr/td").text == "(none)"

    def test_table_numbering_is_shared_with_simpletable(self):
        tree = parse(render_dita(topic(
            "<simpletable><title>S</title><strow><stentry>x</stentry></strow></simpletable>"
            '<table><title>T</title><tgroup cols="1"><tbody><row><entry>y</entry></row></tbody></tgroup></table>'
        )).html)
        labels = [s.text for s in tree.xpath("//span[@class='table--title-label']")]
        assert labels == ["Table 1. ", "Table 2. "]


# ---------------------------------------------------------------------------
# Preprocessing: conref, keyref, filtering
# ---------------------------------------------------------------------------

class TestConref:
    def test_same_file_conref(self):
        result = render_dita(topic(
            '<p conref="#t1/src" outputclass="copy"/><p id="src">Shared <b>text</b></p>'
        ))
        tree = parse(result.html)
        copies = tree.xpath("//p[.='Shared text']")
        assert len(copies) == 2
        assert copies[0].get("class") == "p copy" and copies[0].get("id") is None
        assert result.warnings == []

    def test_conref_chains_are_followed(self):
        result = render_dita(topic('<p conref="#t1/b"/><p id="b" conref="#t1/c"/><p id="c">End</p>'))
        assert len(parse(result.html).xpath("//p[.='End']")) == 3
        assert result.warnings == []

    def test_conref_through_loader_resolves_relative_paths(self):
        files = {
            "shared/lib.dita": '<topic id="lib"><title>L</title><body>'
                               '<note id="n" type="tip"><p conref="more.dita#more/m"/></note></body></topic>',
            "shared/more.dita": '<topic id="more"><title>M</title><body><p id="m">Deep</p></body></topic>',
        }
        requested = []

        def loader(path):
            requested.append(path)
            return files.get(path)

        result = DitaRenderer(loader=loader).render(topic('<note conref="shared/lib.dita#lib/n"/>'))
        tree = parse(result.html)
        assert one(tree, "//div[@class='note tip note_tip']//p").text == "Deep"
        assert requested == ["shared/lib.dita", "shared/more.dita"]

    def test_unresolved_and_circular_conrefs_warn(self):
        result = render_dita(topic('<p conref="missing.dita#x/y">Fallback</p><p id="a" conref="#t1/a"/>'))
        assert one(parse(result.html), "//p[.='Fallback']") is not None
        assert any("missing.dita" in w for w in result.warnings)
        assert any("circular" in w for w in result.warnings)

    def test_conkeyref(self):
        renderer = DitaRenderer(
            keys={"lib": KeyDefinition(href="lib.dita")},
            loader=lambda path: '<topic id="lib"><title>L</title><body><p id="w">Warned</p></body></topic>',
        )
        tree = parse(renderer.render(topic('<p conkeyref="lib/w"/>')).html)
        assert one(tree, "//p").text == "Warned"

    def test_loader_errors_do_not_fail_the_render(self):
        def loader(path):
            raise RuntimeError("repository offline")

        result = DitaRenderer(loader=loader).render(topic('<p conref="x.dita#x/y">Kept</p>'))
        assert "Kept" in result.html
        assert any("repository offline" in w for w in result.warnings)


class TestKeyref:
    def test_keyword_text_and_links(self):
        renderer = DitaRenderer(keys={
            "product": KeyDefinition(text="Acme"),
            "docs": {"href": "https://docs.test", "scope": "external", "text": "the docs"},
            "logo": KeyDefinition(href="img/logo.png"),
        })
        result = renderer.render(topic(
            '<p><keyword keyref="product"/> — see <xref keyref="docs"/>'
            '<image keyref="logo"/> <ph keyref="nope">literal</ph><keyword keyref="gone"/></p>'
        ))
        tree = parse(result.html)
        assert one(tree, "//span[@class='keyword']").text == "Acme"
        link = one(tree, "//a[@class='xref']")
        assert (link.get("href"), link.text, link.get("target")) == ("https://docs.test", "the docs", "_blank")
        assert one(tree, "//img").get("src") == "img/logo.png"
        assert one(tree, "//span[@class='ph']").text == "literal"
        assert len(result.warnings) == 2  # nope, gone

    def test_keys_from_map(self):
        keys = keys_from_map(
            '<map><keydef keys="product prod"><topicmeta><keywords><keyword>Acme</keyword></keywords>'
            '</topicmeta></keydef><keydef keys="product"><topicmeta><keywords><keyword>Ignored</keyword>'
            '</keywords></topicmeta></keydef><topicref keys="install" href="install.dita">'
            "<topicmeta><linktext>Install it</linktext></topicmeta></topicref></map>"
        )
        assert keys["product"] == KeyDefinition(text="Acme")
        assert keys["prod"].text == "Acme"
        assert keys["install"] == KeyDefinition(href="install.dita", text="Install it")


class TestFiltering:
    def test_exclude_by_attribute(self):
        renderer = DitaRenderer(exclude={"audience": ["expert"], "platform": ["windows"]})
        html = renderer.render(topic(
            '<p audience="expert">E</p><p audience="expert novice">Both</p>'
            '<p platform="windows">W</p><p>Always</p> tail'
        )).html
        assert "E</p>" not in html and "W</p>" not in html
        assert "Both" in html and "Always" in html and "tail" in html

    def test_grouped_props_values(self):
        renderer = DitaRenderer(exclude={"os": ["linux"]})
        html = renderer.render(topic('<p product="os(linux)">L</p><p product="os(linux mac)">LM</p>')).html
        assert ">L<" not in html and "LM" in html

    def test_exclusions_from_ditaval(self):
        exclude = exclusions_from_ditaval(
            '<val><prop att="audience" val="expert" action="exclude"/>'
            '<prop att="audience" val="admin" action="exclude"/>'
            '<prop att="platform" val="mac" action="flag"/></val>'
        )
        assert exclude == {"audience": ["expert", "admin"]}


# ---------------------------------------------------------------------------
# Safety: the fragment is inserted into pages
# ---------------------------------------------------------------------------

class TestSafety:
    def test_markup_in_text_is_escaped(self):
        html = render_dita(topic("<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>")).html
        assert "<script" not in html and "&lt;script&gt;" in html

    def test_source_attributes_are_not_copied(self):
        html = render_dita(topic('<p onclick="alert(1)" style="color:red" data-x="1">x</p>')).html
        assert "onclick" not in html and "style" not in html and "data-x" not in html

    @pytest.mark.parametrize("href", [
        "javascript:alert(1)", "JaVaScRiPt:alert(1)", "java\nscript:alert(1)",
        " javascript:alert(1)", "vbscript:msgbox(1)", "data:text/html,<script>alert(1)</script>",
    ])
    def test_unsafe_link_urls_are_not_linked(self, href):
        from xml.sax.saxutils import quoteattr
        result = render_dita(topic(f"<p><xref href={quoteattr(href)} scope='external'>x</xref></p>"))
        tree = parse(result.html)
        assert not tree.xpath("//a")
        assert one(tree, "//span[@class='xref']").text == "x"

    def test_unsafe_image_sources_are_dropped(self):
        result = render_dita(topic(
            '<p><image href="javascript:alert(1)"/><image href="data:image/svg+xml;base64,PHN2Zz4="/>'
            '<image href="data:image/png;base64,iVBORw0KGgo="/></p>'
        ))
        assert [img.get("src") for img in parse(result.html).xpath("//img")] == ["data:image/png;base64,iVBORw0KGgo="]

    def test_resolver_output_is_also_checked(self):
        renderer = DitaRenderer(resolve_href=lambda href, el: "javascript:alert(1)")
        assert "<a " not in renderer.render(topic('<p><xref href="a.dita">a</xref></p>')).html

    def test_foreign_and_namespaced_content_is_dropped(self):
        result = render_dita(topic(
            '<p>A<foreign><script>x</script></foreign>'
            '<svg-container><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg></svg-container>'
            '<object data="x.swf"/></p>'
        ))
        assert "script" not in result.html and "svg" not in result.html and "object" not in result.html
        assert any("SVG" in w for w in result.warnings)

    def test_external_entities_are_not_resolved(self, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("TOP-SECRET")
        xml = (
            f'<!DOCTYPE topic [<!ENTITY xxe SYSTEM "file://{secret}">]>'
            '<topic id="t"><title>T</title><body><p>&xxe;</p></body></topic>'
        )
        try:
            html = render_dita(xml).html
        except DitaParseError:
            return
        assert "TOP-SECRET" not in html


class TestResolver:
    def test_resolve_href_maps_links_and_images(self):
        seen = []

        def resolve(href, element):
            seen.append((href, element.tag))
            if href.endswith(".png"):
                return f"/assets/{href}"
            if href == "drop.dita":
                return None
            return f"/topics/{href.split('.')[0]}"

        tree = parse(DitaRenderer(resolve_href=resolve).render(topic(
            '<p><xref href="install.dita">i</xref> <xref href="drop.dita">d</xref>'
            ' <xref href="#t1">self</xref><image href="a.png"/></p>'
        )).html)
        assert one(tree, "//a[.='i']").get("href") == "/topics/install"
        assert one(tree, "//span[@class='xref']").text == "d"
        assert one(tree, "//a[.='self']").get("href") == "#t1"  # same-topic links never go to the resolver
        assert one(tree, "//img").get("src") == "/assets/a.png"
        assert seen == [("install.dita", "xref"), ("drop.dita", "xref"), ("a.png", "image")]


# ---------------------------------------------------------------------------
# POST /dita/render
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dita_client(_clean_test_db):
    from starlette.testclient import TestClient
    from hop_core.app_factory import create_hop_app
    from tests.conftest import _get_test_settings

    app = create_hop_app(settings_factory=_get_test_settings, include_dita_router=True)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def dita_headers(dita_client):
    from tests.conftest import login, register

    user = register(dita_client)
    return {"Authorization": f"Bearer {login(dita_client, user['email'], user['password'])}"}


class TestRoute:
    def test_not_mounted_by_default(self, client, new_user):
        resp = client.post("/api/v1/dita/render", json={"content": topic("")}, headers=new_user["headers"])
        assert resp.status_code == 404

    def test_requires_authentication(self, dita_client):
        assert dita_client.post("/api/v1/dita/render", json={"content": topic("")}).status_code == 401

    def test_renders_topic(self, dita_client, dita_headers):
        resp = dita_client.post(
            "/api/v1/dita/render",
            json={"content": topic('<p audience="x">Hidden</p><p>Shown</p>'), "exclude": {"audience": ["x"]},
                  "heading_offset": 1},
            headers=dita_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["title"] == "Title" and body["topic_type"] == "topic" and body["topic_id"] == "t1"
        assert "<h2" in body["html"] and "Shown" in body["html"] and "Hidden" not in body["html"]
        assert body["warnings"] == []

    def test_malformed_xml_is_422(self, dita_client, dita_headers):
        resp = dita_client.post("/api/v1/dita/render", json={"content": "<topic>"}, headers=dita_headers)
        assert resp.status_code == 422
        assert "well-formed" in resp.json()["detail"]

    def test_oversized_topic_is_413(self, dita_client, dita_headers):
        from hop_core.api.routes.dita import MAX_TOPIC_BYTES

        big = topic("<p>" + "x" * MAX_TOPIC_BYTES + "</p>")
        resp = dita_client.post("/api/v1/dita/render", json={"content": big}, headers=dita_headers)
        assert resp.status_code == 413
