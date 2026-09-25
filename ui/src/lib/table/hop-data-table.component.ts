import {
  AfterContentInit, AfterViewInit, Component, ContentChildren, Directive, Input,
  OnChanges, QueryList, SimpleChanges, TemplateRef, ViewChild, inject, ChangeDetectionStrategy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatTableDataSource, MatTableModule } from '@angular/material/table';
import { MatSort, MatSortModule, SortDirection } from '@angular/material/sort';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';

/** A cell value the table knows how to sort and filter. */
export type HopTableValue = string | number | boolean | Date | null | undefined;

export interface HopTableColumn<T = any> {
  /** Column id. Also the row property read when `value` is omitted. */
  key: string;
  /** Header text. */
  label: string;
  /** Include in header-click sorting. Default `true`. */
  sortable?: boolean;
  /** Include in the filter's text match. Default `true`. */
  filterable?: boolean;
  /** Value used for display, sorting and filtering. Default `row[key]`. */
  value?: (row: T) => HopTableValue;
  /** Right-align the column (numbers, amounts). */
  align?: 'start' | 'end';
}

/**
 * Custom cell content for one column. The row is the template's implicit
 * context: `<ng-template hopCell="role" let-row>{{ row.role }}</ng-template>`.
 */
@Directive({ selector: 'ng-template[hopCell]', standalone: true })
export class HopTableCellDirective {
  @Input('hopCell') column = '';
  readonly template = inject(TemplateRef);
}

@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-data-table',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatTableModule, MatSortModule, MatFormFieldModule,
    MatInputModule, MatIconModule, MatButtonModule,
  ],
  template: `
    @if (filterable) {
      <div class="table-toolbar">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="filter-field">
          <mat-icon matPrefix>search</mat-icon>
          <input matInput [placeholder]="filterPlaceholder" [attr.aria-label]="filterPlaceholder"
                 [ngModel]="filter" (ngModelChange)="applyFilter($event)">
          @if (filter) {
            <button mat-icon-button matSuffix aria-label="Clear filter" (click)="applyFilter('')">
              <mat-icon>close</mat-icon>
            </button>
          }
        </mat-form-field>
        @if (filter) {
          <span class="match-count">{{ dataSource.filteredData.length }} of {{ dataSource.data.length }}</span>
        }
      </div>
    }

    <div class="table-scroll">
      <table mat-table [dataSource]="dataSource" matSort
             [matSortActive]="sortActive ?? ''" [matSortDirection]="sortDirection">
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
            {{ filter ? 'No rows match “' + filter + '”' : emptyText }}
          </td>
        </tr>
      </table>
    </div>
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
    /* Offset matches the theme's 12px floating-label margin on the field. */
    .match-count { margin-top: 12px; color: var(--text-tertiary); font-size: 0.82rem; white-space: nowrap; }
    .table-scroll { overflow-x: auto; }
    table { width: 100%; }
    .align-end { text-align: right; }
    .empty-row td {
      padding: 24px 16px;
      text-align: center;
      color: var(--text-tertiary);
    }
    .empty-row:hover td { background: transparent; }
    @media (max-width: 768px) {
      .filter-field { width: 100%; }
    }
  `],
})
export class HopDataTableComponent<T = any> implements OnChanges, AfterContentInit, AfterViewInit {
  @Input() columns: HopTableColumn<T>[] = [];
  @Input() data: T[] = [];
  /** Show a text filter above the table that matches across filterable columns. */
  @Input() filterable = false;
  @Input() filterPlaceholder = 'Filter';
  /** Initial sort column key; `null` leaves rows in input order until a header is clicked. */
  @Input() sortActive: string | null = null;
  @Input() sortDirection: SortDirection = 'asc';
  /** Shown when `data` is empty. */
  @Input() emptyText = 'No data';

  @ViewChild(MatSort, { static: true }) sort!: MatSort;
  @ContentChildren(HopTableCellDirective) cellDefs!: QueryList<HopTableCellDirective>;

  readonly dataSource: MatTableDataSource<T> = new MatTableDataSource<T>([]);
  cellTemplates = new Map<string, TemplateRef<any>>();
  columnKeys: string[] = [];
  filter = '';

  constructor() {
    this.dataSource.sortingDataAccessor = (row, key) => this.sortKey(row, key);
    this.dataSource.filterPredicate = (row, term) => this.matches(row, term);
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['columns']) this.columnKeys = this.columns.map(c => c.key);
    if (changes['data']) this.dataSource.data = this.data ?? [];
  }

  ngAfterContentInit(): void {
    this.indexCellTemplates();
    this.cellDefs.changes.subscribe(() => this.indexCellTemplates());
  }

  ngAfterViewInit(): void {
    this.dataSource.sort = this.sort;
  }

  applyFilter(term: string): void {
    this.filter = term;
    this.dataSource.filter = term.trim().toLowerCase();
  }

  valueOf(row: T, col: HopTableColumn<T>): HopTableValue {
    return col.value ? col.value(row) : (row as any)?.[col.key];
  }

  private sortKey(row: T, key: string): string | number {
    const col = this.columns.find(c => c.key === key);
    const v = col ? this.valueOf(row, col) : (row as any)?.[key];
    if (v == null) return '';
    if (v instanceof Date) return v.getTime();
    if (typeof v === 'number') return v;
    if (typeof v === 'boolean') return v ? 1 : 0;
    return String(v).toLowerCase();
  }

  private matches(row: T, term: string): boolean {
    if (!term) return true;
    return this.columns
      .filter(c => c.filterable !== false)
      .some(c => {
        const v = this.valueOf(row, c);
        return v != null && String(v).toLowerCase().includes(term);
      });
  }

  private indexCellTemplates(): void {
    this.cellTemplates = new Map(this.cellDefs.map(d => [d.column, d.template]));
  }
}
