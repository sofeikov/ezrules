export function splitFieldPath(fieldPath: string): string[] {
  return fieldPath.split('.');
}

export function fieldPathLeafName(fieldPath: string): string {
  const segments = splitFieldPath(fieldPath);
  return segments[segments.length - 1];
}

export function dottedPathAlias(fieldPath: string): string {
  return fieldPath.replace(/\./g, '_');
}

export function setNestedValue(target: Record<string, unknown>, fieldPath: string, value: unknown): void {
  const segments = splitFieldPath(fieldPath);
  let current: Record<string, unknown> = target;

  segments.slice(0, -1).forEach((segment) => {
    const nextValue = current[segment];
    if (typeof nextValue !== 'object' || nextValue === null || Array.isArray(nextValue)) {
      current[segment] = {};
    }
    current = current[segment] as Record<string, unknown>;
  });

  current[segments[segments.length - 1]] = value;
}

export function buildHighlightedFieldPaths(fieldPaths: string[]): Set<string> {
  const highlightedPaths = new Set<string>();

  fieldPaths.forEach((fieldPath) => {
    const segments = splitFieldPath(fieldPath);
    segments.forEach((_, index) => {
      highlightedPaths.add(segments.slice(0, index + 1).join('.'));
    });
  });

  return highlightedPaths;
}
