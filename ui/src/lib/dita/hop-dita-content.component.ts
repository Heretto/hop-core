import {
  Component, ElementRef, EventEmitter, Input, OnChanges, OnDestroy, OnInit, Output,
  SimpleChanges, ViewChild, inject, ChangeDetectionStrategy } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Subscription } from 'rxjs';
import { DitaExclusions, HopDitaService, RenderedDitaTopic } from './hop-dita.service';
import { sanitizeDitaHtml } from './hop-dita-sanitize';

/** A link inside rendered DITA was activated. Call `event.preventDefault()` to handle it yourself. */
export interface HopDitaLinkEvent {
  href: string;
  /** True for `scope="external"` links and absolute http(s)/mailto URLs. */
  external: boolean;
  event: MouseEvent;
}

/**
 * Displays rendered DITA with the design-system typography for topics:
 * notes, figures, tables, steps, code blocks and the rest.
 *
 * Give it either `html` (already rendered — typically by
 * `hop_core.dita.DitaRenderer` in your backend) or `dita` (raw topic XML,
 * rendered through `POST /dita/render`). Links to ids inside the topic scroll
 * in place; every other link is reported through `linkClick` first, so an app
 * can route topic-to-topic links itself.
 */
@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-dita-content',
  standalone: true,
  // The content styles live in the theme (hop-core-theme → _dita.scss): the
  // HTML is inserted outside Angular's view, so emulated encapsulation would
  // not reach it, and they are too large for a per-component style budget.
  template: `
    @if (error) {
      <div class="hop-dita-error" role="alert">{{ error }}</div>
    }
    <div #host class="hop-dita" [attr.lang]="lang" (click)="onClick($event)"></div>
  `,
  styles: [`
    :host { display: block; }
    .hop-dita-error {
      margin-bottom: 16px; padding: 10px 12px; border-radius: 8px;
      background: var(--color-error-bg); color: var(--color-error-text);
      border: 1px solid var(--color-error-border);
    }
  `],
})
export class HopDitaContentComponent implements OnChanges, OnInit, OnDestroy {
  private ditaService = inject(HopDitaService);
  private document = inject(DOCUMENT);

  /** Rendered DITA HTML. Ignored when `dita` is set. */
  @Input() html: string | null = null;
  /** Raw DITA topic XML, rendered server-side. */
  @Input() dita: string | null = null;
  /** Conditional-processing exclusions applied when rendering `dita`. */
  @Input() exclude: DitaExclusions | null = null;
  /** Heading levels to push down when rendering `dita` (1 → the title is an h2). */
  @Input() headingOffset = 0;

  /** Emits after `dita` renders — title, shortdesc and warnings for the host page. */
  @Output() rendered = new EventEmitter<RenderedDitaTopic>();
  @Output() linkClick = new EventEmitter<HopDitaLinkEvent>();

  @ViewChild('host', { static: true }) private host!: ElementRef<HTMLElement>;

  error: string | null = null;
  lang: string | null = null;
  private request?: Subscription;
  private initialized = false;

  ngOnInit(): void {
    this.initialized = true;
    this.update();
  }

  ngOnChanges(changes: SimpleChanges): void {
    // The first pass runs before the host element exists; ngOnInit renders it.
    if (!this.initialized) return;
    const ditaChanged = changes['dita'] || changes['exclude'] || changes['headingOffset'];
    if (this.dita == null || ditaChanged) this.update();
  }

  ngOnDestroy(): void {
    this.request?.unsubscribe();
  }

  private update(): void {
    this.request?.unsubscribe();
    this.error = null;
    if (this.dita != null) {
      this.renderDita(this.dita);
    } else {
      this.lang = null;
      this.show(this.html ?? '');
    }
  }

  private renderDita(content: string): void {
    this.request = this.ditaService
      .render(content, { exclude: this.exclude ?? undefined, heading_offset: this.headingOffset })
      .subscribe({
        next: result => {
          this.lang = result.lang;
          this.show(result.html);
          this.rendered.emit(result);
        },
        error: (err: HttpErrorResponse) => {
          this.show('');
          this.error = typeof err.error?.detail === 'string'
            ? err.error.detail
            : 'This topic could not be rendered.';
        },
      });
  }

  private show(html: string): void {
    const host = this.host.nativeElement;
    host.replaceChildren(sanitizeDitaHtml(html, this.document));
  }

  onClick(event: MouseEvent): void {
    const anchor = (event.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null;
    if (!anchor || !this.host.nativeElement.contains(anchor)) return;
    const href = anchor.getAttribute('href') ?? '';

    if (href.startsWith('#')) {
      // A bare fragment resolves against <base href>, so the browser would leave
      // the page. Scroll to the target inside this topic instead.
      event.preventDefault();
      const target = this.findById(decodeURIComponent(href.slice(1)));
      target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }

    const external = anchor.target === '_blank' || /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(href);
    this.linkClick.emit({ href, external, event });
  }

  private findById(id: string): HTMLElement | null {
    for (const el of Array.from(this.host.nativeElement.querySelectorAll<HTMLElement>('[id]'))) {
      if (el.id === id) return el;
    }
    return null;
  }
}
