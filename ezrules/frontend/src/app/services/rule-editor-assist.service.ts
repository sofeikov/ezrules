import { Injectable } from '@angular/core';
import { combineLatest, Observable, of } from 'rxjs';
import { catchError, map, shareReplay } from 'rxjs/operators';
import { FieldTypeService } from './field-type.service';
import { FeatureService } from './feature.service';
import { OutcomeService } from './outcome.service';
import { UserListService } from './user-list.service';

export interface RuleEditorFieldSuggestion {
  name: string;
  observedJsonType: string;
}

export interface RuleEditorListSuggestion {
  name: string;
  entryCount: number;
}

export interface RuleEditorOutcomeSuggestion {
  name: string;
  severityRank: number;
}

export interface RuleEditorFeatureSuggestion {
  path: string;
  aggregation: string;
  entityKey: string;
  windowLabel: string;
}

export interface RuleEditorAssistData {
  fields: RuleEditorFieldSuggestion[];
  features: RuleEditorFeatureSuggestion[];
  lists: RuleEditorListSuggestion[];
  outcomes: RuleEditorOutcomeSuggestion[];
}

@Injectable({
  providedIn: 'root'
})
export class RuleEditorAssistService {
  private assistData$?: Observable<RuleEditorAssistData>;

  constructor(
    private fieldTypeService: FieldTypeService,
    private featureService: FeatureService,
    private outcomeService: OutcomeService,
    private userListService: UserListService
  ) { }

  getAssistData(): Observable<RuleEditorAssistData> {
    if (!this.assistData$) {
      this.assistData$ = combineLatest({
        observations: this.fieldTypeService.getObservations().pipe(catchError(() => of([]))),
        features: this.featureService.getFeatures().pipe(catchError(() => of([]))),
        outcomes: this.outcomeService.getOutcomes().pipe(catchError(() => of({ outcomes: [] }))),
        lists: this.userListService.getUserLists().pipe(catchError(() => of([])))
      }).pipe(
        map(({ observations, features, outcomes, lists }) => ({
          fields: observations
            .slice()
            .sort((left, right) => {
              const byField = left.field_name.localeCompare(right.field_name);
              if (byField !== 0) {
                return byField;
              }
              return left.observed_json_type.localeCompare(right.observed_json_type);
            })
            .map((observation) => ({
              name: observation.field_name,
              observedJsonType: observation.observed_json_type,
            })),
          features: features
            .filter((feature) => feature.status === 'active')
            .sort((left, right) => left.available_as.localeCompare(right.available_as))
            .map((feature) => ({
              path: feature.available_as.replace(/^stat\[/, '').replace(/\]$/, ''),
              aggregation: feature.aggregation_type,
              entityKey: feature.entity_key,
              windowLabel: feature.window_label,
            })),
          lists: lists
            .slice()
            .sort((left, right) => left.name.localeCompare(right.name))
            .map((list) => ({
              name: list.name,
              entryCount: list.entry_count,
            })),
          outcomes: outcomes.outcomes
            .slice()
            .sort((left, right) => left.severity_rank - right.severity_rank || left.outcome_name.localeCompare(right.outcome_name))
            .map((outcome) => ({
              name: outcome.outcome_name,
              severityRank: outcome.severity_rank,
            })),
        })),
        shareReplay(1)
      );
    }

    return this.assistData$;
  }
}
