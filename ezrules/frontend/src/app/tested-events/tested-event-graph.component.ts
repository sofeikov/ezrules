import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, ElementRef, Input, OnChanges, OnDestroy, SimpleChanges, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import type { Core, ElementDefinition } from 'cytoscape';
import {
  TestedEventGraphEdge,
  TestedEventGraphNode,
  TestedEventGraphResponse,
  TestedEventService,
} from '../services/tested-event.service';

@Component({
  selector: 'app-tested-event-graph',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="mt-6 rounded-lg border border-gray-200 bg-white" data-testid="tested-event-graph-panel">
      <div class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-4 py-3">
        <div>
          <h3 class="text-sm font-semibold text-gray-900">Event graph</h3>
          <p class="text-xs text-gray-500">Click an entity node to expand linked events.</p>
        </div>
        <div class="flex items-center gap-3">
          <label class="flex items-center gap-2 text-xs text-gray-600">
            <span>Max events</span>
            <input
              type="number"
              min="1"
              max="100"
              [(ngModel)]="maxEvents"
              (change)="reload()"
              class="w-20 rounded border border-gray-300 px-2 py-1 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </label>
          <label class="flex items-center gap-2 text-xs text-gray-600">
            <span>Hops</span>
            <input
              type="number"
              min="1"
              max="5"
              [(ngModel)]="maxHops"
              (change)="reload()"
              class="w-16 rounded border border-gray-300 px-2 py-1 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </label>
          <button
            type="button"
            (click)="fit()"
            class="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
          >
            Fit
          </button>
          <button
            type="button"
            (click)="reload()"
            class="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
          >
            Reset
          </button>
        </div>
      </div>

      <div *ngIf="error" class="border-b border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        {{ error }}
      </div>
      <div *ngIf="truncated" class="border-b border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        Graph expansion reached the max event cap.
      </div>
      <div *ngIf="selectedNodeLabel" class="border-b border-blue-100 bg-blue-50 px-4 py-2 text-xs text-blue-800">
        Selected {{ selectedNodeLabel }}
      </div>

      <div class="relative h-[520px]">
        <div #graphContainer class="h-full w-full" data-testid="tested-event-graph-canvas"></div>
        <div *ngIf="loading" class="absolute inset-0 flex items-center justify-center bg-white/70">
          <div class="h-8 w-8 animate-spin rounded-full border-b-2 border-blue-600"></div>
        </div>
      </div>
    </div>
  `,
})
export class TestedEventGraphComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input({ required: true }) evaluationDecisionId!: number;
  @ViewChild('graphContainer') graphContainer!: ElementRef<HTMLDivElement>;

  maxEvents = 25;
  maxHops = 3;
  loading = false;
  error = '';
  truncated = false;
  selectedNodeLabel = '';

  private cy: Core | null = null;
  private viewReady = false;
  private expandedEntityIds = new Set<string>();

  constructor(private testedEventService: TestedEventService) {}

  ngAfterViewInit(): void {
    this.viewReady = true;
    void this.initializeGraph().then(() => this.reload());
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['evaluationDecisionId'] && this.viewReady) {
      this.reload();
    }
  }

  ngOnDestroy(): void {
    this.cy?.destroy();
    this.cy = null;
  }

  reload(): void {
    if (!this.viewReady || !this.evaluationDecisionId) {
      return;
    }
    this.expandedEntityIds.clear();
    this.selectedNodeLabel = '';
    this.loadGraph(true);
  }

  fit(): void {
    this.cy?.fit(undefined, 40);
  }

  private async initializeGraph(): Promise<void> {
    if (this.cy) {
      return;
    }

    const cytoscapeModule = await import('cytoscape');
    this.cy = cytoscapeModule.default({
      container: this.graphContainer.nativeElement,
      elements: [],
      style: [
        {
          selector: 'node',
          style: {
            'background-color': '#64748b',
            'border-color': '#334155',
            'border-width': 1,
            color: '#111827',
            content: 'data(label)',
            'font-size': 28,
            'min-zoomed-font-size': 0,
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.95,
            'text-background-padding': '5px',
            'text-margin-y': 13,
            'text-max-width': '240px',
            'text-outline-color': '#ffffff',
            'text-outline-width': 2,
            'text-wrap': 'wrap',
            'text-valign': 'bottom',
            height: 44,
            width: 44,
          },
        },
        {
          selector: 'node[kind = "event"]',
          style: {
            shape: 'round-rectangle',
            'background-color': '#2563eb',
            'border-color': '#1d4ed8',
            height: 52,
            width: 104,
          },
        },
        {
          selector: 'node[root]',
          style: {
            'background-color': '#dc2626',
            'border-color': '#991b1b',
            'border-width': 3,
          },
        },
        {
          selector: 'node[kind = "entity"]',
          style: {
            shape: 'ellipse',
            'background-color': '#14b8a6',
            'border-color': '#0f766e',
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-color': '#f59e0b',
            'border-width': 4,
          },
        },
        {
          selector: 'edge',
          style: {
            'curve-style': 'bezier',
            'line-color': '#cbd5e1',
            'target-arrow-color': '#cbd5e1',
            'target-arrow-shape': 'triangle',
            width: 2,
          },
        },
      ],
      layout: this.graphLayout(false),
      minZoom: 0.25,
      maxZoom: 2,
    });

    this.cy.on('tap', 'node', (event) => {
      const data = event.target.data() as TestedEventGraphNode;
      this.selectedNodeLabel = data.label;
      if (data.kind === 'entity' && data.entity_type && data.entity_value_hash) {
        this.expandEntity(data);
      }
    });
  }

  private expandEntity(node: TestedEventGraphNode): void {
    if (this.expandedEntityIds.has(node.id)) {
      return;
    }
    this.loadGraph(false, node);
  }

  private loadGraph(reset: boolean, expandNode?: TestedEventGraphNode): void {
    this.loading = true;
    this.error = '';
    const maxEvents = this.normalizedMaxEvents();
    const maxHops = this.normalizedMaxHops();
    this.testedEventService.getTestedEventGraph(this.evaluationDecisionId, {
      maxEvents,
      maxHops,
      expandEntityType: expandNode?.entity_type ?? undefined,
      expandEntityValueHash: expandNode?.entity_value_hash ?? undefined,
    }).subscribe({
      next: (response) => {
        this.applyGraph(response, reset);
        if (expandNode) {
          this.expandedEntityIds.add(expandNode.id);
        }
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load event graph.';
        this.loading = false;
      },
    });
  }

  private applyGraph(response: TestedEventGraphResponse, reset: boolean): void {
    if (!this.cy) {
      return;
    }
    this.truncated = response.truncated;
    if (reset) {
      this.cy.elements().remove();
    }

    const existingIds = new Set(this.cy.elements().map((element) => element.id()));
    const elements: ElementDefinition[] = [];
    for (const node of response.nodes) {
      if (!existingIds.has(node.id)) {
        elements.push({ group: 'nodes', data: node });
      }
    }
    for (const edge of response.edges) {
      if (!existingIds.has(edge.id)) {
        elements.push({ group: 'edges', data: edge });
      }
    }

    if (elements.length > 0) {
      this.cy.add(elements);
      this.cy.layout(this.graphLayout(true)).run();
    } else {
      this.cy.fit(undefined, 40);
    }
  }

  private graphLayout(animate: boolean) {
    return {
      name: 'cose',
      animate,
      animationDuration: animate ? 250 : 0,
      idealEdgeLength: 145,
      nodeRepulsion: 95000,
      nodeOverlap: 35,
      padding: 65,
    };
  }

  private normalizedMaxEvents(): number {
    const parsed = Number(this.maxEvents);
    if (!Number.isFinite(parsed)) {
      this.maxEvents = 25;
      return 25;
    }
    this.maxEvents = Math.min(100, Math.max(1, Math.floor(parsed)));
    return this.maxEvents;
  }

  private normalizedMaxHops(): number {
    const parsed = Number(this.maxHops);
    if (!Number.isFinite(parsed)) {
      this.maxHops = 3;
      return 3;
    }
    this.maxHops = Math.min(5, Math.max(1, Math.floor(parsed)));
    return this.maxHops;
  }
}
