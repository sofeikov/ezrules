export interface PermissionRequirement {
  allOf?: string[];
  anyOf?: string[];
}

export const ROUTE_PERMISSION_REQUIREMENTS = {
  dashboard: { allOf: ['view_rules', 'view_outcomes'] },
  rules: { allOf: ['view_rules'] },
  ruleCreate: { allOf: ['create_rule'] },
  eventTester: { allOf: ['view_rules', 'submit_test_events'] },
  labels: { allOf: ['view_labels'] },
  outcomes: { allOf: ['view_outcomes'] },
  testedEvents: { allOf: ['view_rules'] },
  userLists: { allOf: ['view_lists'] },
  labelAnalytics: { allOf: ['view_labels'] },
  ruleQuality: { allOf: ['view_rules', 'view_labels'] },
  settings: { allOf: ['view_roles'] },
  users: { allOf: ['view_users'] },
  roles: { allOf: ['view_roles'] },
  audit: { allOf: ['access_audit_trail'] },
  fieldTypes: { allOf: ['view_field_types'] },
  shadowRules: { allOf: ['view_rules'] },
  rollouts: { allOf: ['view_rules'] },
  apiKeys: { allOf: ['manage_api_keys'] },
} as const satisfies Record<string, PermissionRequirement>;

export const ACTION_PERMISSION_REQUIREMENTS = {
  createRule: { allOf: ['create_rule'] },
  modifyRule: { allOf: ['modify_rule'] },
  reorderRules: { allOf: ['reorder_rules'] },
  pauseRules: { allOf: ['pause_rules'] },
  promoteRules: { allOf: ['promote_rules'] },
  deleteRule: { allOf: ['delete_rule'] },
  createLabel: { allOf: ['create_label'] },
  deleteLabel: { allOf: ['delete_label'] },
  createOutcome: { allOf: ['create_outcome'] },
  deleteOutcome: { allOf: ['delete_outcome'] },
  manageNeutralOutcome: { allOf: ['manage_neutral_outcome'] },
  createList: { allOf: ['create_list'] },
  modifyList: { allOf: ['modify_list'] },
  deleteList: { allOf: ['delete_list'] },
  viewUsers: { allOf: ['view_users'] },
  createUser: { allOf: ['create_user'] },
  modifyUser: { allOf: ['modify_user'] },
  deleteUser: { allOf: ['delete_user'] },
  manageUserRoles: { allOf: ['manage_user_roles'] },
  viewRoles: { allOf: ['view_roles'] },
  createRole: { allOf: ['create_role'] },
  deleteRole: { allOf: ['delete_role'] },
  managePermissions: { allOf: ['manage_permissions'] },
  modifyFieldTypes: { allOf: ['modify_field_types'] },
  deleteFieldType: { allOf: ['delete_field_type'] },
  manageApiKeys: { allOf: ['manage_api_keys'] },
  submitTestEvents: { allOf: ['submit_test_events'] },
} as const satisfies Record<string, PermissionRequirement>;

export const PERMISSION_LABELS: Record<string, string> = {
  create_rule: 'Create rules',
  modify_rule: 'Modify rules',
  reorder_rules: 'Reorder rules',
  pause_rules: 'Pause rules',
  promote_rules: 'Promote rules',
  delete_rule: 'Delete rules',
  view_rules: 'View rules',
  submit_test_events: 'Submit test events',
  create_outcome: 'Create outcomes',
  modify_outcome: 'Modify outcomes',
  delete_outcome: 'Delete outcomes',
  view_outcomes: 'View outcomes',
  manage_neutral_outcome: 'Manage neutral outcome',
  create_list: 'Create user lists',
  modify_list: 'Modify user lists',
  delete_list: 'Delete user lists',
  view_lists: 'View user lists',
  create_label: 'Create labels',
  modify_label: 'Modify labels',
  delete_label: 'Delete labels',
  view_labels: 'View labels',
  access_audit_trail: 'Access audit trail',
  view_users: 'View users',
  create_user: 'Create users',
  modify_user: 'Modify users',
  delete_user: 'Delete users',
  manage_user_roles: 'Manage user roles',
  view_roles: 'View roles',
  create_role: 'Create roles',
  modify_role: 'Modify roles',
  delete_role: 'Delete roles',
  manage_permissions: 'Manage permissions',
  view_field_types: 'View field types',
  modify_field_types: 'Modify field types',
  delete_field_type: 'Delete field types',
  manage_api_keys: 'Manage API keys',
};

export function hasPermissionRequirement(
  permissions: readonly string[],
  requirement?: PermissionRequirement | null
): boolean {
  if (!requirement) {
    return true;
  }

  if (requirement.allOf && requirement.allOf.some((permission) => !permissions.includes(permission))) {
    return false;
  }

  if (requirement.anyOf && !requirement.anyOf.some((permission) => permissions.includes(permission))) {
    return false;
  }

  return true;
}

export function describePermissions(permissions: readonly string[]): string[] {
  return permissions.map((permission) => PERMISSION_LABELS[permission] ?? permission.replace(/_/g, ' '));
}
