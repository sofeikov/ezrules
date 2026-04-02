import { Injectable } from '@angular/core';
import { combineLatest, Observable, of } from 'rxjs';
import { catchError, map, shareReplay } from 'rxjs/operators';
import { FieldTypeService } from './field-type.service';
import { UserListService } from './user-list.service';

export interface RuleEditorFieldSuggestion {
  name: string;
  observedJsonType: string;
  occurrenceCount: number;
  lastSeen: string | null;
}

export interface RuleEditorListSuggestion {
  name: string;
  entryCount: number;
}

export interface RuleEditorAssistData {
  fields: RuleEditorFieldSuggestion[];
  lists: RuleEditorListSuggestion[];
}

@Injectable({
  providedIn: 'root'
})
export class RuleEditorAssistService {
  private assistData$?: Observable<RuleEditorAssistData>;

  constructor(
    private fieldTypeService: FieldTypeService,
    private userListService: UserListService
  ) { }

  getAssistData(): Observable<RuleEditorAssistData> {
    if (!this.assistData$) {
      this.assistData$ = combineLatest({
        observations: this.fieldTypeService.getObservations().pipe(catchError(() => of([]))),
        lists: this.userListService.getUserLists().pipe(catchError(() => of([])))
      }).pipe(
        map(({ observations, lists }) => ({
          fields: observations
            .slice()
            .sort((left, right) => {
              const byCount = right.occurrence_count - left.occurrence_count;
              if (byCount !== 0) {
                return byCount;
              }
              return left.field_name.localeCompare(right.field_name);
            })
            .map((observation) => ({
              name: observation.field_name,
              observedJsonType: observation.observed_json_type,
              occurrenceCount: observation.occurrence_count,
              lastSeen: observation.last_seen,
            })),
          lists: lists
            .slice()
            .sort((left, right) => left.name.localeCompare(right.name))
            .map((list) => ({
              name: list.name,
              entryCount: list.entry_count,
            })),
        })),
        shareReplay(1)
      );
    }

    return this.assistData$;
  }
}
