import { Component, OnInit, OnDestroy, AfterViewInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Chart, registerables } from 'chart.js';
import { DashboardService, ChartDataset } from '../services/dashboard.service';
import { SidebarComponent } from '../components/sidebar.component';

Chart.register(...registerables);

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, SidebarComponent],
  templateUrl: './dashboard.component.html'
})
export class DashboardComponent implements OnInit, AfterViewInit, OnDestroy {
  activeRulesCount: number = 0;
  loading: boolean = true;
  chartsLoading: boolean = true;
  error: string | null = null;
  selectedAggregation: string = '6h';

  transactionVolumeLabels: string[] = [];
  transactionVolumeData: number[] = [];

  outcomeDatasets: ChartDataset[] = [];
  outcomeTimeLabels: string[] = [];

  private charts: Map<string, Chart> = new Map();
  private canvasReady = false;

  readonly aggregations = [
    { value: '1h', label: 'Last 1 Hour' },
    { value: '6h', label: 'Last 6 Hours' },
    { value: '12h', label: 'Last 12 Hours' },
    { value: '24h', label: 'Last 24 Hours' },
    { value: '30d', label: 'Last 30 Days' }
  ];

  constructor(private dashboardService: DashboardService, private cdr: ChangeDetectorRef) {}

  ngOnInit(): void {
    this.loadActiveRules();
    this.loadCharts();
  }

  ngAfterViewInit(): void {
    this.canvasReady = true;
    if (!this.chartsLoading) {
      this.cdr.detectChanges();
      setTimeout(() => this.renderCharts(), 0);
    }
  }

  ngOnDestroy(): void {
    this.destroyCharts();
  }

  loadActiveRules(): void {
    this.dashboardService.getActiveRulesCount().subscribe({
      next: (count) => {
        this.activeRulesCount = count;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load active rules count.';
        this.loading = false;
      }
    });
  }

  loadCharts(): void {
    this.chartsLoading = true;
    let completed = 0;
    const total = 2;

    const checkDone = () => {
      completed++;
      if (completed >= total) {
        this.chartsLoading = false;
        if (this.canvasReady) {
          this.cdr.detectChanges();
          setTimeout(() => this.renderCharts(), 0);
        }
      }
    };

    this.dashboardService.getTransactionVolume(this.selectedAggregation).subscribe({
      next: (response) => {
        this.transactionVolumeLabels = response.labels;
        this.transactionVolumeData = response.data;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load transaction volume data.';
        checkDone();
      }
    });

    this.dashboardService.getOutcomesDistribution(this.selectedAggregation).subscribe({
      next: (response) => {
        this.outcomeTimeLabels = response.labels;
        this.outcomeDatasets = response.datasets;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load outcomes distribution data.';
        checkDone();
      }
    });
  }

  onAggregationChange(event: Event): void {
    this.selectedAggregation = (event.target as HTMLSelectElement).value;
    this.loadCharts();
  }

  private renderCharts(): void {
    this.destroyCharts();

    // Render transaction volume chart
    const tvCanvas = document.getElementById('transactionVolumeChart') as HTMLCanvasElement;
    if (tvCanvas) {
      const ctx = tvCanvas.getContext('2d');
      if (ctx) {
        const chart = new Chart(ctx, {
          type: 'line',
          data: {
            labels: this.transactionVolumeLabels,
            datasets: [{
              label: 'Transaction Volume',
              data: this.transactionVolumeData,
              borderColor: 'rgb(59, 130, 246)',
              backgroundColor: 'rgba(59, 130, 246, 0.1)',
              tension: 0.3,
              fill: true
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
              legend: { display: false },
              title: { display: false }
            },
            scales: {
              y: {
                beginAtZero: true,
                ticks: { precision: 0 }
              },
              x: {
                ticks: { maxRotation: 45, minRotation: 45 }
              }
            }
          }
        });
        this.charts.set('transactionVolume', chart);
      }
    }

    // Render outcome charts (one per outcome)
    this.outcomeDatasets.forEach((dataset, idx) => {
      const canvas = document.getElementById(`outcomeChart_${idx}`) as HTMLCanvasElement;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const chart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: this.outcomeTimeLabels,
          datasets: [{
            label: dataset.label,
            data: dataset.data,
            borderColor: dataset.borderColor,
            backgroundColor: dataset.backgroundColor,
            tension: 0.3,
            fill: true
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            legend: { display: false },
            title: { display: false }
          },
          scales: {
            y: {
              beginAtZero: true,
              ticks: { precision: 0 }
            },
            x: {
              ticks: { maxRotation: 45, minRotation: 45 }
            }
          }
        }
      });
      this.charts.set(`outcome_${dataset.label}`, chart);
    });
  }

  private destroyCharts(): void {
    this.charts.forEach(chart => chart.destroy());
    this.charts.clear();
  }
}
