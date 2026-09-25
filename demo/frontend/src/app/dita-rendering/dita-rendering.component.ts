import { Component, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { DitaExclusions, HopDitaContentComponent, RenderedDitaTopic } from '@heretto/hop-ui';

const TASK = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">
<task id="install">
  <title>Installing the agent</title>
  <shortdesc>Install and start the agent on a Linux host.</shortdesc>
  <taskbody>
    <prereq>You need root access and <keyword>Python 3.11</keyword> or later<fn>Earlier
      versions are not tested.</fn>.</prereq>
    <context>
      <p>The agent runs as a service. See <xref href="#install/ports"/> before you begin.</p>
      <note type="important">Stop any older agent first.</note>
    </context>
    <steps>
      <step><cmd>Download the package.</cmd>
        <info><codeblock outputclass="language-bash">curl -LO https://example.com/agent.tar.gz</codeblock></info>
      </step>
      <step importance="optional"><cmd>Verify the checksum with <userinput>sha256sum</userinput>.</cmd></step>
      <step><cmd>Open <menucascade><uicontrol>Settings</uicontrol><uicontrol>Services</uicontrol></menucascade>
        and start the agent.</cmd>
        <stepresult>The status shows <systemoutput>running</systemoutput>.</stepresult>
      </step>
    </steps>
    <result>
      <table id="ports" frame="all">
        <title>Ports the agent uses</title>
        <tgroup cols="3">
          <colspec colname="c1" colwidth="1*"/><colspec colname="c2" colwidth="1*"/>
          <colspec colname="c3" colwidth="3*"/>
          <thead><row><entry>Port</entry><entry>Protocol</entry><entry>Purpose</entry></row></thead>
          <tbody>
            <row><entry>8080</entry><entry>HTTP</entry><entry>Admin console</entry></row>
            <row><entry>9443</entry><entry>HTTPS</entry><entry>Agent API</entry></row>
          </tbody>
        </tgroup>
      </table>
      <p audience="expert">Expert tip: tune the worker pool in <filepath>/etc/agent.conf</filepath>.</p>
    </result>
  </taskbody>
</task>`;

const CONCEPT = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="versioning">
  <title>Versioning policy</title>
  <shortdesc>How version numbers are assigned.</shortdesc>
  <conbody>
    <p>Releases follow <term>semantic versioning</term>: <codeph>MAJOR.MINOR.PATCH</codeph>.</p>
    <dl>
      <dlentry><dt>Major</dt><dd>Incompatible API changes.</dd></dlentry>
      <dlentry><dt>Minor</dt><dd>New, backwards-compatible functionality.</dd></dlentry>
      <dlentry><dt>Patch</dt><dd>Backwards-compatible fixes.</dd></dlentry>
    </dl>
    <fig id="flow" frame="all">
      <title>Release flow</title>
      <lines>main
  → release branch
    → tag</lines>
    </fig>
    <note type="tip">Pin exact versions in production.</note>
    <hazardstatement type="caution">
      <messagepanel>
        <typeofhazard>Skipping major versions</typeofhazard>
        <consequence>Migrations may be missed.</consequence>
        <howtoavoid>Upgrade one major version at a time.</howtoavoid>
      </messagepanel>
    </hazardstatement>
  </conbody>
  <related-links>
    <link href="upgrade.dita" type="task"><linktext>Upgrading</linktext></link>
    <link href="https://semver.org" scope="external" format="html"><linktext>semver.org</linktext></link>
  </related-links>
</concept>`;

const REFERENCE = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">
<reference id="config">
  <title>Configuration settings</title>
  <shortdesc>Settings read from <filepath>agent.conf</filepath>.</shortdesc>
  <refbody>
    <refsyn><codeblock>agent --config &lt;path&gt; [--verbose]</codeblock></refsyn>
    <properties>
      <property><proptype>int</proptype><propvalue>port</propvalue><propdesc>Listen port. Default 8080.</propdesc></property>
      <property><proptype>bool</proptype><propvalue>tls</propvalue><propdesc>Serve HTTPS.</propdesc></property>
    </properties>
    <section id="env">
      <title>Environment variables</title>
      <simpletable relcolwidth="1* 2*">
        <sthead><stentry>Variable</stentry><stentry>Overrides</stentry></sthead>
        <strow><stentry><varname>AGENT_PORT</varname></stentry><stentry>port</stentry></strow>
        <strow><stentry><varname>AGENT_TLS</varname></stentry><stentry>tls</stentry></strow>
      </simpletable>
    </section>
  </refbody>
</reference>`;

const SAMPLES: Record<string, string> = { task: TASK, concept: CONCEPT, reference: REFERENCE };

@Component({
  selector: 'app-dita-rendering',
  imports: [
    FormsModule, RouterLink, MatCardModule, MatButtonModule, MatButtonToggleModule,
    MatFormFieldModule, MatInputModule, MatIconModule, MatSlideToggleModule,
    HopDitaContentComponent,
  ],
  template: `
    <div class="hop-page">
      <a mat-button routerLink="/dashboard" class="back-link">
        <mat-icon>arrow_back</mat-icon>
        Back to Dashboard
      </a>

      <h1>DITA Rendering</h1>
      <p class="subtitle">
        <code>hop_core.dita.DitaRenderer</code> turns a DITA topic into HTML the way the
        DITA Open Toolkit's HTML5 transform does, and <code>&lt;hop-dita-content&gt;</code>
        shows it with the design system. Edit the topic and render it.
      </p>

      <div class="controls">
        <mat-button-toggle-group [value]="sample" (change)="load($event.value)" aria-label="Sample topic">
          <mat-button-toggle value="task">Task</mat-button-toggle>
          <mat-button-toggle value="concept">Concept</mat-button-toggle>
          <mat-button-toggle value="reference">Reference</mat-button-toggle>
        </mat-button-toggle-group>
        <mat-slide-toggle [(ngModel)]="hideExpert" (change)="render()">
          Exclude <code>audience="expert"</code>
        </mat-slide-toggle>
      </div>

      <div class="workbench">
        <mat-card class="editor">
          <mat-card-content>
            <mat-form-field appearance="outline" class="source">
              <mat-label>DITA source</mat-label>
              <textarea matInput [(ngModel)]="source" rows="28" spellcheck="false"></textarea>
            </mat-form-field>
            <button mat-flat-button color="primary" type="button" (click)="render()">
              <mat-icon>play_arrow</mat-icon>
              Render
            </button>
          </mat-card-content>
        </mat-card>

        <mat-card class="preview">
          <mat-card-content>
            @if (warnings.length) {
              <div class="callout warning">
                <mat-icon>warning</mat-icon>
                <span>{{ warnings.join(' · ') }}</span>
              </div>
            }
            <hop-dita-content [dita]="rendered" [exclude]="exclude" (rendered)="onRendered($event)" />
          </mat-card-content>
        </mat-card>
      </div>

      <h2>Using it in your app</h2>
      <mat-card>
        <mat-card-content>
          <div class="hop-code-panel"><pre>{{ usageSnippet }}</pre></div>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    .back-link { margin-bottom: 16px; }
    h1 { margin-bottom: 8px; }
    .subtitle { color: var(--text-secondary); margin-bottom: 24px; max-width: 760px; }
    h2 { margin: 32px 0 16px; }
    .controls { display: flex; flex-wrap: wrap; align-items: center; gap: 24px; margin-bottom: 16px; }
    .workbench { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: 16px; align-items: start; }
    @media (max-width: 1024px) { .workbench { grid-template-columns: minmax(0, 1fr); } }
    .source { width: 100%; }
    .source textarea { font-family: var(--font-mono); font-size: 12.5px; line-height: 1.5; }
    .callout.warning {
      display: flex; gap: 8px; align-items: flex-start; padding: 10px 12px; margin-bottom: 16px;
      border-radius: 8px; background: var(--color-warning-bg); color: var(--color-warning-text);
      border: 1px solid var(--color-warning-border);
    }
  `],
})
export class DitaRenderingComponent {
  sample = 'task';
  source = TASK;
  rendered = TASK;
  hideExpert = false;
  exclude: DitaExclusions | null = null;
  warnings: string[] = [];

  load(sample: string): void {
    this.sample = sample;
    this.source = SAMPLES[sample];
    this.render();
  }

  render(): void {
    this.exclude = this.hideExpert ? { audience: ['expert'] } : null;
    this.rendered = this.source;
  }

  onRendered(result: RenderedDitaTopic): void {
    this.warnings = result.warnings;
  }

  usageSnippet = `# Backend — render where the content lives (pip install 'hop-core[dita]')
from hop_core.dita import DitaRenderer, keys_from_map

renderer = DitaRenderer(
    keys=keys_from_map(map_xml),                 # resolve keyref / conkeyref
    loader=lambda path: repo.read(path),         # resolve conrefs to other files
    resolve_href=lambda href, el: f"/docs/{href}",  # map links and images to app URLs
    exclude={"audience": ["expert"]},            # or exclusions_from_ditaval(ditaval_xml)
    heading_offset=1,                            # topic title becomes <h2>
)
result = renderer.render(topic_xml)   # .html  .title  .shortdesc  .warnings

# Or let the frontend send raw DITA:  create_hop_app(..., include_dita_router=True)

<!-- Frontend -->
<hop-dita-content [html]="topic.html" (linkClick)="route($event)" />
<hop-dita-content [dita]="topicXml" [exclude]="{ audience: ['expert'] }" />`;
}
