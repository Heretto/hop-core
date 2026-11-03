import {
  AfterContentInit, Component, ContentChildren, EventEmitter, Input,
  OnChanges, OnDestroy, OnInit, Output, QueryList, SimpleChanges,
  TemplateRef, ChangeDetectionStrategy, inject, ChangeDetectorRef,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatTableModule } from '@angular/material/table';
import { MatSort, MatSortModule, Sort, SortDirection } from '@angular/material/sort';
import { MatPaginator, MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Subject } from 'rxjs';
import { debounceTime, takeUntil } from 'rxjs/operators';
import { HopTableCellDirective, HopTableColumn, HopTableValue } from './hop-data-table.component';

/** Parameters emitted on every page, sort, or filter change.
 *
 *  Map these to your API's query params (the hop-core backend helper
 *  expects camelCase: pageSize, sortBy, sortDir, filter).
 */
export interface HopTableParams {
  page: number;
  pageSize: number;
  sortBy: string | null;
  sortDir: 'asc' | 'desc';
  filter: string;
}

/**
 * Server-side paginated table.
 *
 * The host supplies the **current page's** `items` and the `total` record
 * count.  When the user pages, sorts, or types a filter the component emits
 * `paramsChange` — the host calls its API with those params and updates
 * `items` and `total`.
 *
 * ```html
 * <hop-paged-table
 *   [columns]="cols"
 *   [items]="page.items"
 *   [total]="page.total"
 *   [loading]="loading"
 *   [filterable]="true"
 *   (paramsChange)="load($event)">
 *   <ng-template hopCell="role" let-row>{{ row.role }}</ng-template>
 * </hop-paged-table>
 * ```
 *
 * Custom cells use the same `hopCell` directive as `hop-data-table`.
 * Sorting is entirely server-driven: the sort arrows are visual indicators
 * only; no client-side reordering happens.
 */
@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-paged-table',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatTableModule, MatSortModule, MatPaginatorModule,
    MatFormFieldModule, MatInputModule, MatIconModule, MatButtonModule, MatProgressBarModule,
  ],
  template: `
    @if (filterable) {
      <div class="table-toolbar">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="filter-field">
          <mat-icon matPrefix>search</mat-icon>
          <input matInput [placeholder]="filterPlaceholder" [attr.aria-label]="filterPlaceholder"
                 [ngModel]="filter" (ngModelChange)="onFilterInput($event)">
          @if (filter) {
            <button mat-icon-button matSuffix aria-label="Clear filter" (click)="clearFilter()">
              <mat-icon>close</mat-icon>
            </button>
          }
        </mat-form-field>
      </div>
    }

    <div class="table-wrapper" [class.is-loading]="loading">
      @if (loading) {
        <mat-progress-bar class="loading-bar" mode="indeterminate"></mat-progress-bar>
      }
      <div class="table-scroll">
        <table mat-table [dataSource]="items"
               matSort [matSortActive]="params.sortBy ?? ''"
               [matSortDirection]="params.sortDir"
               (matSortChange)="onSortChange($event)">
          @for (col of columns; track col.key) {
            <ng-container [matColumnDef]="col.key">
              <th mat-header-cell *matHeaderCellDef
                  mat-sort-header [disabled]="col.sortable === false"
                  [arrowPosition]="col.align === 'end' ? 'before' : 'after'"
                  [class.align-end]="col.align === 'end'">{{ col.label }}</th>
              <td mat-cell *matCellDef="let row" [class.align-end]="col.align === 'end'">
                @if (cellTemplates.get(col.key); as tpl) {
                  <ng-container *ngTemplateOutlet="tpl; context: { $implicit: row }"></ng-container>
                } @else {
                  {{ valueOf(row, col) }}
                }
              </td>
            </ng-container>
          }
          <tr mat-header-row *matHeaderRowDef="columnKeys"></tr>
          <tr mat-row *matRowDef="let row; columns: columnKeys"></tr>
          <tr class="mat-mdc-row empty-row" *matNoDataRow>
            <td class="mat-mdc-cell" [attr.colspan]="columnKeys.length">
              {{ emptyText }}
            </td>
          </tr>
        </table>
      </div>
    </div>

    <mat-paginator
      [length]="total"
      [pageSize]="params.pageSize"
      [pageSizeOptions]="pageSizeOptions"
      [pageIndex]="params.page - 1"
      (page)="onPageChange($event)"
      showFirstLastButtons>
    </mat-paginator>
  `,
  styles: [`
    :host { display: block; }

    .table-toolbar {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 0 16px 12px;
    }
    .filter-field { width: 280px; max-width: 100%; }
    .filter-field mat-icon[matPrefix] { color: var(--text-tertiary); padding: 0 4px 0 8px; }

    .table-wrapper { position: relative; }
    .loading-bar {
      position: absolute;
      top: 0; left: 0; right: 0;
      z-index: 1;
    }
    .is-loading .table-scroll { opacity: 0.5; pointer-events: none; transition: opacity 150ms ease; }

    .table-scroll { overflow-x: auto; }
    table { width: 100%; }
    .align-end { text-align: right; }

    .empty-row td {
      padding: 24px 16px;
      text-align: center;
      color: var(--text-tertiary);
    }
    .empty-row:hover td { background: transparent; }

    mat-paginator {
      border-top: 1px solid var(--border-light);
      background: transparent;
    }

    @media (max-width: 768px) {
      .filter-field { width: 100%; }
    }
  `],
})
export class HopPagedTableComponent<T = any> implements OnInit, OnChanges, AfterContentInit, OnDestroy {
  @Input() columns: HopTableColumn<T>[] = [];
  /** Current page of items — provided by the host after each API call. */
  @Input() items: T[] = [];
  /** Total record count across all pages (from the server). */
  @Input() total = 0;
  @Input() loading = false;
  @Input() filterable = false;
  @Input() filterPlaceholder = 'Filter';
  @Input() pageSizeOptions = [10, 25, 50, 100];
  /** Initial page size; also used when the host resets the table. */
  @Input() pageSize = 25;
  @Input() emptyText = 'No data';
  /** Initial sort column key (matches a `HopTableColumn.key`). */
  @Input() sortActive: string | null = null;
  @Input() sortDir: SortDirection = 'asc';

  /** Emits on every page, sort, or filter change.  Call your API here. */
  @Output() paramsChange = new EventEmitter<HopTableParams>();

  @ContentChildren(HopTableCellDirective) cellDefs!: QueryList<HopTableCellDirective>;

  cellTemplates = new Map<string, TemplateRef<any>>();
  columnKeys: string[] = [];
  filter = '';

  params: HopTableParams = {
    page: 1,
    pageSize: 25,
    sortBy: null,
    sortDir: 'asc',
    filter: '',
  };

  private filterSubject = new Subject<string>();
  private destroy$ = new Subject<void>();
  private cdr = inject(ChangeDetectorRef);

  ngOnInit(): void {
    this.params = {
      page: 1,
      pageSize: this.pageSize,
      sortBy: this.sortActive,
      sortDir: (this.sortDir || 'asc') as 'asc' | 'desc',
      filter: '',
    };

    this.filterSubject.pipe(
      debounceTime(300),
      takeUntil(this.destroy$),
    ).subscribe(value => {
      this.params = { ...this.params, page: 1, filter: value };
      this.paramsChange.emit({ ...this.params });
    });

    // Emit initial params so the host fetches the first page immediately.
    this.paramsChange.emit({ ...this.params });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['columns']) {
      this.columnKeys = this.columns.map(c => c.key);
    }
  }

  ngAfterContentInit(): void {
    this.indexCellTemplates();
    this.cellDefs.changes.subscribe(() => this.indexCellTemplates());
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onSortChange(sort: Sort): void {
    this.params = {
      ...this.params,
      page: 1,
      sortBy: sort.active && sort.direction ? sort.active : null,
      sortDir: (sort.direction as 'asc' | 'desc') || 'asc',
    };
    this.paramsChange.emit({ ...this.params });
  }

  onPageChange(event: PageEvent): void {
    this.params = { ...this.params, page: event.pageIndex + 1, pageSize: event.pageSize };
    this.paramsChange.emit({ ...this.params });
  }

  onFilterInput(value: string): void {
    this.filter = value;
    this.filterSubject.next(value);
  }

  clearFilter(): void {
    this.filter = '';
    this.filterSubject.next('');
  }

  valueOf(row: T, col: HopTableColumn<T>): HopTableValue {
    return col.value ? col.value(row) : (row as any)?.[col.key];
  }

  private indexCellTemplates(): void {
    this.cellTemplates = new Map(this.cellDefs.map(d => [d.column, d.template]));
  }
}
