import { Injectable } from '@angular/core';
import { Observable, forkJoin, of } from 'rxjs';
import { catchError, map, shareReplay } from 'rxjs/operators';
import { dottedPathAlias, fieldPathLeafName, setNestedValue } from '../utils/field-paths';
import { FieldObservation, FieldTypeConfig, FieldTypeService } from './field-type.service';

type SampleValue = boolean | number | string;

interface FieldTypeMetadata {
  configuredTypes: Map<string, FieldTypeConfig>;
  observedTypes: Map<string, FieldObservation[]>;
}

const DEFAULT_DATETIME_SAMPLE = '2025-01-15T10:30:00Z';
const OBSERVED_TYPE_MAP: Record<string, string> = {
  bool: 'boolean',
  float: 'float',
  int: 'integer',
  str: 'string',
};

const EXACT_SAMPLE_VALUES: Record<string, SampleValue> = {
  account_age_days: 7,
  amount: 875.5,
  beneficiary_age_days: 1,
  beneficiary_country: 'IR',
  billing_country: 'US',
  card_present: 0,
  channel: 'web',
  currency: 'USD',
  customer_avg_amount_30d: 140.0,
  customer_country: 'US',
  customer_id: 'cust_demo_001',
  customer_std_amount_30d: 30.0,
  decline_count_24h: 7,
  device_age_days: 1,
  device_trust_score: 18,
  distance_from_home_km: 4200,
  email_age_days: 4,
  email_domain: 'mailinator.com',
  has_3ds: 0,
  ip_country: 'BR',
  ip_proxy_score: 92,
  is_guest_checkout: 1,
  is_verified: false,
  local_hour: 2,
  manual_review_hits_30d: 2,
  merchant_category: 'gift_cards',
  merchant_country: 'US',
  merchant_id: 'mrc_cardhub',
  password_reset_age_hours: 2,
  prior_chargebacks_180d: 2,
  receive_country: 'MX',
  score: 0.92,
  'customer.id': 'cust_demo_001',
  'customer.country': 'US',
  'customer.profile.age': 34,
  'customer.profile.segment': 'established',
  'customer.account.age_days': 180,
  'customer.account.email_age_days': 365,
  'customer.account.prior_chargebacks_180d': 0,
  'customer.behavior.avg_amount_30d': 140.0,
  'customer.behavior.std_amount_30d': 30.0,
  'sender.id': 'sender_demo_001',
  'sender.country': 'US',
  'sender.account.age_days': 90,
  'sender.origin.country': 'BR',
  'sender.device.age_days': 1,
  'sender.device.trust_score': 18,
  send_country: 'US',
  shipping_country: 'MX',
  txn_type: 'wallet_cashout',
  txn_velocity_10m: 10,
  txn_velocity_1h: 6,
  unique_cards_24h: 5,
};

@Injectable({
  providedIn: 'root'
})
export class RuleTestDataService {
  private metadata$?: Observable<FieldTypeMetadata>;

  constructor(private fieldTypeService: FieldTypeService) {}

  buildExampleJson(params: string[]): Observable<string> {
    if (!params.length) {
      return of(JSON.stringify({}, null, 2));
    }

    return this.getMetadata().pipe(
      map((metadata) => JSON.stringify(buildRuleTestSamplePayload(params, metadata), null, 2))
    );
  }

  private getMetadata(): Observable<FieldTypeMetadata> {
    if (!this.metadata$) {
      this.metadata$ = forkJoin({
        configs: this.fieldTypeService.getConfigs().pipe(catchError(() => of([]))),
        observations: this.fieldTypeService.getObservations().pipe(catchError(() => of([]))),
      }).pipe(
        map(({ configs, observations }) => buildFieldTypeMetadata(configs, observations)),
        shareReplay(1)
      );
    }

    return this.metadata$;
  }
}

export function buildRuleTestSamplePayload(
  params: string[],
  metadata: FieldTypeMetadata
): Record<string, unknown> {
  const samplePayload: Record<string, unknown> = {};

  params.forEach((param) => {
    const fieldType = resolveFieldType(param, metadata);
    setNestedValue(samplePayload, param, buildSampleValue(param, fieldType));
  });

  return samplePayload;
}

function buildFieldTypeMetadata(
  configs: FieldTypeConfig[],
  observations: FieldObservation[]
): FieldTypeMetadata {
  const configuredTypes = new Map(configs.map((config) => [config.field_name, config]));
  const observedTypes = new Map<string, FieldObservation[]>();

  observations.forEach((observation) => {
    const current = observedTypes.get(observation.field_name) ?? [];
    current.push(observation);
    observedTypes.set(observation.field_name, current);
  });

  return {
    configuredTypes,
    observedTypes,
  };
}

function resolveFieldType(fieldName: string, metadata: FieldTypeMetadata): string {
  const configuredType = metadata.configuredTypes.get(fieldName)?.configured_type;
  if (configuredType && configuredType !== 'compare_as_is') {
    return configuredType;
  }

  const observedType = pickObservedType(fieldName, metadata.observedTypes.get(fieldName) ?? []);
  if (observedType) {
    return observedType;
  }

  return inferFieldTypeFromName(fieldName);
}

function pickObservedType(fieldName: string, observations: FieldObservation[]): string | null {
  const observedTypes = observations
    .map((observation) => OBSERVED_TYPE_MAP[observation.observed_json_type])
    .filter((value): value is string => Boolean(value));

  if (observedTypes.length === 0) {
    return null;
  }

  const uniqueObservedTypes = [...new Set(observedTypes)];
  if (uniqueObservedTypes.length === 1) {
    return uniqueObservedTypes[0];
  }

  const inferredType = inferFieldTypeFromName(fieldName);
  if (inferredType !== 'string') {
    return inferredType;
  }

  const observedPriority = ['float', 'integer', 'boolean', 'string'];
  return observedPriority.find((candidate) => uniqueObservedTypes.includes(candidate)) ?? uniqueObservedTypes[0];
}

function inferFieldTypeFromName(fieldName: string): string {
  const normalized = fieldName.toLowerCase();

  if (
    normalized.includes('date') ||
    normalized.includes('time') ||
    normalized.includes('timestamp') ||
    normalized.endsWith('_at')
  ) {
    return 'datetime';
  }

  if (normalized.startsWith('is_') || normalized.startsWith('has_') || normalized.endsWith('_flag')) {
    return 'boolean';
  }

  if (
    normalized.includes('amount') ||
    normalized.includes('ratio') ||
    normalized.includes('avg') ||
    normalized.includes('mean') ||
    normalized.includes('std')
  ) {
    return 'float';
  }

  if (
    normalized.includes('count') ||
    normalized.includes('age') ||
    normalized.includes('hour') ||
    normalized.includes('velocity') ||
    normalized.includes('distance') ||
    normalized.includes('score')
  ) {
    return 'integer';
  }

  return 'string';
}

function buildSampleValue(fieldName: string, fieldType: string): SampleValue {
  const exactValue =
    EXACT_SAMPLE_VALUES[fieldName] ??
    EXACT_SAMPLE_VALUES[dottedPathAlias(fieldName)] ??
    EXACT_SAMPLE_VALUES[fieldPathLeafName(fieldName)];
  if (exactValue !== undefined) {
    return coerceSampleValue(exactValue, fieldType, fieldName);
  }

  switch (fieldType) {
    case 'boolean':
      return booleanSampleForField(fieldName);
    case 'datetime':
      return DEFAULT_DATETIME_SAMPLE;
    case 'float':
      return floatSampleForField(fieldName);
    case 'integer':
      return integerSampleForField(fieldName);
    default:
      return stringSampleForField(fieldName);
  }
}

function coerceSampleValue(value: SampleValue, fieldType: string, fieldName: string): SampleValue {
  switch (fieldType) {
    case 'boolean':
      return typeof value === 'boolean' ? value : Boolean(value);
    case 'datetime':
      return typeof value === 'string' ? value : DEFAULT_DATETIME_SAMPLE;
    case 'float':
      return typeof value === 'number' ? value : floatSampleForField(fieldName);
    case 'integer':
      return typeof value === 'number' ? Math.round(value) : integerSampleForField(fieldName);
    default:
      return typeof value === 'string' ? value : String(value);
  }
}

function booleanSampleForField(fieldName: string): boolean {
  const normalized = fieldName.toLowerCase();

  if (normalized.includes('trusted') || normalized.includes('enabled')) {
    return true;
  }

  return false;
}

function floatSampleForField(fieldName: string): number {
  const normalized = fieldName.toLowerCase();

  if (normalized.includes('amount')) {
    return 875.5;
  }
  if (normalized.includes('ratio')) {
    return 2.75;
  }
  if (normalized.includes('score')) {
    return 88.5;
  }

  return 12.5;
}

function integerSampleForField(fieldName: string): number {
  const normalized = fieldName.toLowerCase();

  if (normalized.includes('hour')) {
    return 2;
  }
  if (normalized.includes('age')) {
    return 7;
  }
  if (normalized.includes('velocity')) {
    return 6;
  }
  if (normalized.includes('distance')) {
    return 4200;
  }
  if (normalized.includes('score')) {
    return 88;
  }

  return 3;
}

function stringSampleForField(fieldName: string): string {
  const normalized = fieldName.toLowerCase();
  const fieldLeaf = fieldPathLeafName(fieldName);

  if (normalized.endsWith('_country') || normalized.includes('country')) {
    if (normalized.includes('shipping')) {
      return 'MX';
    }
    if (normalized.includes('beneficiary')) {
      return 'IR';
    }
    if (normalized.includes('ip')) {
      return 'BR';
    }
    return 'US';
  }

  if (normalized.includes('currency')) {
    return 'USD';
  }

  if (normalized.includes('category')) {
    return 'gift_cards';
  }

  if (normalized.includes('email') && normalized.includes('domain')) {
    return 'mailinator.com';
  }

  if (normalized.includes('txn') && normalized.includes('type')) {
    return 'wallet_cashout';
  }

  if (normalized.endsWith('_id') || normalized.includes('reference')) {
    return `demo_${fieldLeaf}`;
  }

  return `sample_${fieldLeaf}`;
}
