import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

interface TestGroup {
  suite: string;
  file: string;
  note?: string;
  tests: string[];
}

@Component({
  selector: 'app-dita-docs',
  imports: [RouterLink, MatCardModule, MatButtonModule, MatIconModule],
  template: `
    <div class="dita-docs">
      <a mat-button routerLink="/dashboard" class="back-link">
        <mat-icon>arrow_back</mat-icon>
        Back to Dashboard
      </a>

      <h1>DITA Validation</h1>
      <p class="subtitle">
        <code>hop_core.dita</code> gives every hop-core app production-grade
        DITA 1.3 validation and AI-driven correction — install the
        <code>hop-core[dita]</code> extra and import two classes.
      </p>

      <!-- CAPABILITIES -->
      <h2>What you get</h2>
      <div class="capability-grid">
        <mat-card>
          <mat-card-content class="capability">
            <span class="hop-icon-badge"><mat-icon>fact_check</mat-icon></span>
            <div>
              <h4>DTD validation</h4>
              <p class="text-secondary">
                <code>DitaValidator.validate_with_dtd()</code> validates against the
                official OASIS DITA 1.3 grammars via <code>xmllint</code> — the full
                DTD content model, with precise line-level errors. The complete
                OASIS tree ships inside the hop-core package; there is nothing to
                download or configure.
              </p>
            </div>
          </mat-card-content>
        </mat-card>

        <mat-card>
          <mat-card-content class="capability">
            <span class="hop-icon-badge accent"><mat-icon>account_tree</mat-icon></span>
            <div>
              <h4>Structural fallback</h4>
              <p class="text-secondary">
                When <code>xmllint</code> isn't installed, validation degrades
                gracefully to lxml-based structural checks: root element, required
                id/title/body, section titles, list contents, text placement.
              </p>
            </div>
          </mat-card-content>
        </mat-card>

        <mat-card>
          <mat-card-content class="capability">
            <span class="hop-icon-badge success"><mat-icon>healing</mat-icon></span>
            <div>
              <h4>Deterministic auto-fixes</h4>
              <p class="text-secondary">
                <code>auto_fix_common_issues()</code> repairs the classics without an
                LLM call: missing XML declaration and DOCTYPE, unescaped ampersands,
                invalid ID formats.
              </p>
            </div>
          </mat-card-content>
        </mat-card>

        <mat-card>
          <mat-card-content class="capability">
            <span class="hop-icon-badge warning"><mat-icon>crisis_alert</mat-icon></span>
            <div>
              <h4>Root-element enforcement</h4>
              <p class="text-secondary">
                <code>ensure_topic_root()</code> guarantees a valid topic-type root.
                Bare <code>&lt;section&gt;</code> output from an LLM — the classic
                failure mode — is deterministically re-wrapped in a proper
                <code>&lt;topic&gt;</code> shell, preserving the original id and title.
              </p>
            </div>
          </mat-card-content>
        </mat-card>

        <mat-card>
          <mat-card-content class="capability">
            <span class="hop-icon-badge info"><mat-icon>sync</mat-icon></span>
            <div>
              <h4>AI correction loop</h4>
              <p class="text-secondary">
                <code>DitaCorrectionService.validate_and_correct_with_ai()</code> feeds
                invalid DITA back through your LLM with the specific validation
                errors until it passes — deterministic fixes first, targeted
                corrections next, strict regeneration as a last resort, all behind
                a safety cap.
              </p>
            </div>
          </mat-card-content>
        </mat-card>

        <mat-card>
          <mat-card-content class="capability">
            <span class="hop-icon-badge tertiary-badge"><mat-icon>extension</mat-icon></span>
            <div>
              <h4>Any AI provider</h4>
              <p class="text-secondary">
                The correction service is provider-agnostic: anything with an
                <code>async generate(request)</code> method returning
                <code>.content</code> satisfies the <code>SupportsGenerate</code>
                protocol — Anthropic, OpenAI, Gemini, or a stub in your tests.
              </p>
            </div>
          </mat-card-content>
        </mat-card>
      </div>

      <!-- USAGE -->
      <h2>Using it in your app</h2>
      <mat-card class="section-card">
        <mat-card-content>
          <p class="text-secondary">
            Install the extra (plus <code>xmllint</code> for full DTD validation:
            <code>apt-get install libxml2-utils</code> /
            <code>brew install libxml2</code>), then:
          </p>
          <div class="hop-code-panel"><pre>{{ usageSnippet }}</pre></div>
        </mat-card-content>
      </mat-card>

      <!-- TESTS -->
      <h2>How we test it</h2>
      <p class="section-note text-secondary">
        Effective validation is only as good as its test suite. hop-core ships
        three DITA suites (79 tests) that run on every
        <code>./run_tests.sh</code> / <code>make test</code>; DTD-level
        assertions are exercised with a real <code>xmllint</code> and the
        packaged grammars — not mocks.
      </p>

      @for (group of testGroups; track group.suite) {
        <mat-card class="section-card">
          <mat-card-header>
            <mat-card-title>{{ group.suite }}</mat-card-title>
            <mat-card-subtitle><code>{{ group.file }}</code></mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            <ul class="test-list">
              @for (test of group.tests; track test) {
                <li>
                  <mat-icon class="check">check_circle</mat-icon>
                  <span>{{ test }}</span>
                </li>
              }
            </ul>
            @if (group.note) {
              <p class="group-note text-tertiary">{{ group.note }}</p>
            }
          </mat-card-content>
        </mat-card>
      }
    </div>
  `,
  styles: [`
    .dita-docs { max-width: 900px; margin: 0 auto; padding-bottom: 48px; }
    .back-link { margin-bottom: 16px; }
    h1 { margin-bottom: 8px; }
    .subtitle { color: var(--text-secondary); margin-bottom: 32px; }
    h2 { margin: 32px 0 16px; }
    .section-note { margin-bottom: 16px; }

    .capability-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 16px;
    }
    .capability { display: flex; gap: 14px; }
    .capability h4 { margin-bottom: 4px; }
    .capability p { margin-bottom: 0; line-height: 1.6; }
    .tertiary-badge { background: var(--color-tertiary-bg); color: var(--color-tertiary); }

    .section-card { margin-bottom: 16px; }
    .section-card p { line-height: 1.6; }

    .test-list { list-style: none; margin: 0; padding: 0; }
    .test-list li {
      display: flex; align-items: flex-start; gap: 10px;
      padding: 6px 0; color: var(--text-secondary); line-height: 1.5;
      border-bottom: 1px solid var(--border-light);
    }
    .test-list li:last-child { border-bottom: none; }
    .test-list .check {
      color: var(--color-success); flex: none;
      font-size: 20px; width: 20px; height: 20px; margin-top: 1px;
    }
    .group-note { margin: 12px 0 0; font-size: 0.85rem; }
  `],
})
export class DitaDocsComponent {
  usageSnippet = `# requirements.txt
hop-core[dita]

# Validate
from hop_core.dita import DitaValidator

validator = DitaValidator()                      # bundled OASIS DTDs
is_valid, errors = validator.validate_with_dtd(dita_content)

# Validate + correct with your LLM until it passes
from hop_core.dita import DitaCorrectionService

service = DitaCorrectionService(ai_service=my_ai, validator=validator)
content, is_valid, log = await service.validate_and_correct_with_ai(
    dita_content,
    max_iterations=10,   # safety cap — pass your own setting
)`;

  testGroups: TestGroup[] = [
    {
      suite: 'Validator unit suite',
      file: 'tests/test_dita_validator.py',
      tests: [
        'Packaged-resource guard: the bundled OASIS DTD directory resolves and every grammar the validator references exists — a packaging mistake can never silently weaken validation',
        'DOCTYPE injection: PUBLIC/SYSTEM doctypes are correctly replaced with local SYSTEM paths, preserving XML-declaration position and topic type',
        'DTD validation catches real violations: missing id attribute, missing title, unknown elements, HTML tags like <span>, inline elements directly in <body>, malformed XML',
        'Known-good topics (with and without shortdesc) pass DTD validation cleanly',
        'Errors are returned as structured lists with line-level detail, ready for AI correction',
        'Structural fallback: when xmllint is absent, missing ids/titles/bodies, untitled sections, and empty lists are still caught',
        'Auto-fix pipeline: adds XML declaration and DOCTYPE, escapes bare ampersands without double-escaping, repairs numeric IDs — and the fixed output passes DTD validation',
        'Regression guard: validate_with_dtd() provably takes the xmllint path when available and only falls back when it is not',
      ],
    },
    {
      suite: 'Root-element regression suite',
      file: 'tests/test_dita_root_element.py',
      note: 'Locks in the fix for a real production bug where LLM corrections returned bare <section> elements and invalid roots were saved.',
      tests: [
        'Root detection: valid topic-type roots recognized; single and multi <section> roots rejected (multiple top-level elements are never silently accepted)',
        'ensure_topic_root(): bare sections are re-wrapped in a valid <topic> with all content preserved, ids sanitized to DITA-legal format, and no double-nested <body>',
        'Wrapped output passes both structural and DTD validation',
        'The correction service never returns an invalid root — even when the (mocked) AI keeps responding with bare sections',
        'Original topic id and title survive when the LLM strips the wrapper',
        'Loop-until-valid: invalid DITA is fed back through the LLM until a response validates (verified call-by-call with a stub AI)',
        'Safety cap: a persistently-failing LLM stops at max_iterations, reports is_valid=False, and still hands back a valid <topic> root',
        'Deterministic fixes need zero LLM calls when the problem is mechanical',
        'The stub AI service is a plain class — living proof any provider satisfies the SupportsGenerate protocol',
      ],
    },
    {
      suite: 'Fixture validation corpus',
      file: 'tests/test_dita_fixture_validation.py',
      note: 'Known-answer corpus of 23 .dita files; DTD-level, so it runs against real xmllint and skips gracefully where xmllint is unavailable.',
      tests: [
        '9 valid fixtures across topic, concept, task, and reference — minimal and full-featured variants — must pass with zero errors',
        '14 invalid fixtures must fail with error messages naming the offending element: missing titles, title after body, unknown/HTML elements, wrong body element per topic type, nested concepts, steps missing <cmd>, empty lists, malformed XML',
        'Inventory guard: every fixture referenced by the test tables must exist on disk',
      ],
    },
  ];
}
