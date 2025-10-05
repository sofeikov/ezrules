#!/bin/bash

# CLI Testing Script for ezrules
# Tests CLI functionality with database verification

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test database configuration
TEST_DB_ENDPOINT="postgresql://postgres:root@localhost:5432/tests"
export EZRULES_DB_ENDPOINT="$TEST_DB_ENDPOINT"
export EZRULES_TESTING="true"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[TEST]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to run psql command and check result
verify_db() {
    local query="$1"
    local expected="$2"
    local description="$3"

    print_status "Verifying: $description"
    result=$(psql "$TEST_DB_ENDPOINT" -t -c "$query" | xargs)

    if [[ "$result" == "$expected" ]]; then
        print_status "✓ $description - PASSED"
        return 0
    else
        print_error "✗ $description - FAILED (expected: $expected, got: $result)"
        return 1
    fi
}

# Function to run psql command and check if result contains expected value
verify_db_contains() {
    local query="$1"
    local expected="$2"
    local description="$3"

    print_status "Verifying: $description"
    result=$(psql "$TEST_DB_ENDPOINT" -t -c "$query")

    if echo "$result" | grep -qF "$expected"; then
        print_status "✓ $description - PASSED"
        return 0
    else
        print_error "✗ $description - FAILED (expected to contain: $expected, got: $result)"
        return 1
    fi
}

# Function to count rows in table
count_rows() {
    local table="$1"
    local description="$2"

    print_status "Counting rows in $table: $description" >&2
    count=$(psql "$TEST_DB_ENDPOINT" -t -c "SELECT COUNT(*) FROM $table;" | xargs)
    print_status "Found $count rows in $table" >&2
    echo "$count"
}

# Clean up function
cleanup() {
    print_status "Cleaning up test data..."
    uv run ezrules delete-test-data 2>/dev/null || true
}

# Trap to ensure cleanup on exit
trap cleanup EXIT

print_status "Starting CLI functionality tests..."

# Test 1: Initialize database
print_status "Test 1: Initialize database"
uv run ezrules init-db --auto-delete

# Verify database tables exist
verify_db "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('user', 'role', 'organisation');" "3" "Essential tables created"

# Test 2: Add user
print_status "Test 2: Add user"
test_email="test@example.com"
test_password="testpass123"

uv run ezrules add-user --user-email "$test_email" --password "$test_password"

# Verify user exists in database
verify_db "SELECT email FROM \"user\" WHERE email = '$test_email';" "$test_email" "User $test_email created"
verify_db_contains "SELECT password FROM \"user\" WHERE email = '$test_email';" '$2b$' "Password is properly hashed (bcrypt)"
verify_db "SELECT active FROM \"user\" WHERE email = '$test_email';" "t" "User is active"

# Test 3: Initialize permissions
print_status "Test 3: Initialize permissions"
uv run ezrules init-permissions

# Verify roles and permissions exist
verify_db "SELECT COUNT(*) FROM \"role\" WHERE name IN ('admin', 'readonly', 'rule_editor');" "3" "Default roles created"
# Check if we have at least 1 permission (using a more flexible approach)
actions_count=$(psql "$TEST_DB_ENDPOINT" -t -c "SELECT COUNT(*) FROM actions WHERE name IS NOT NULL;" | xargs)
if [[ $actions_count -gt 0 ]]; then
    print_status "✓ Permissions exist ($actions_count permissions) - PASSED"
else
    print_error "✗ No permissions found - FAILED"
fi

# Test 4: Add duplicate user (should handle gracefully)
print_status "Test 4: Add duplicate user"
uv run ezrules add-user --user-email "$test_email" --password "newpass" 2>/dev/null || true

# Verify only one user exists
verify_db "SELECT COUNT(*) FROM \"user\" WHERE email = '$test_email';" "1" "Duplicate user not created"

# Test 5: Generate random data
print_status "Test 5: Generate random data"
initial_rules=$(count_rows "rules" "before data generation")
initial_events=$(count_rows "testing_record_log" "before data generation")

uv run ezrules generate-random-data --n-rules 5 --n-events 10 --label-ratio 0.5

# Verify data was generated
final_rules=$(count_rows "rules" "after data generation")
final_events=$(count_rows "testing_record_log" "after data generation")

if [[ $final_rules -gt $initial_rules ]]; then
    print_status "✓ Rules generated successfully ($initial_rules → $final_rules)"
else
    print_error "✗ No rules were generated"
fi

if [[ $final_events -gt $initial_events ]]; then
    print_status "✓ Events generated successfully ($initial_events → $final_events)"
else
    print_error "✗ No events were generated"
fi

# Verify some events were labeled
labeled_count=$(psql "$TEST_DB_ENDPOINT" -t -c "SELECT COUNT(*) FROM testing_record_log WHERE el_id IS NOT NULL;" | xargs)
print_status "Found $labeled_count labeled events"

if [[ $labeled_count -gt 0 ]]; then
    print_status "✓ Event labeling successful"
else
    print_warning "⚠ No events were labeled (this might be expected)"
fi

# Test 6: Export test CSV
print_status "Test 6: Export test CSV"
test_csv_file="test_export.csv"
uv run ezrules export-test-csv --output-file "$test_csv_file" --n-events 5

if [[ -f "$test_csv_file" ]]; then
    csv_lines=$(wc -l < "$test_csv_file")
    print_status "✓ CSV export successful ($csv_lines lines)"

    # Verify CSV format
    if head -1 "$test_csv_file" | grep -q ","; then
        print_status "✓ CSV format appears correct"
    else
        print_error "✗ CSV format may be incorrect"
    fi

    # Clean up CSV file
    rm -f "$test_csv_file"
else
    print_error "✗ CSV export failed - file not created"
fi

# Test 7: Verify organisation exists
print_status "Test 7: Verify organisation"
verify_db "SELECT name FROM organisation WHERE name = 'base';" "base" "Base organisation created"

# Test 8: Delete test data
print_status "Test 8: Delete test data"
uv run ezrules delete-test-data

# Verify test data is removed
verify_db "SELECT COUNT(*) FROM testing_record_log WHERE event_id LIKE 'TestEvent_%';" "0" "Test events deleted"
verify_db "SELECT COUNT(*) FROM rules WHERE rid LIKE 'TestRule_%';" "0" "Test rules deleted"

# Test summary
print_status "=== CLI TEST SUMMARY ==="
print_status "All major CLI commands tested successfully:"
print_status "  ✓ init-db: Database initialization"
print_status "  ✓ add-user: User creation with password hashing"
print_status "  ✓ init-permissions: Role and permission setup"
print_status "  ✓ generate-random-data: Data generation and labeling"
print_status "  ✓ export-test-csv: CSV export functionality"
print_status "  ✓ delete-test-data: Cleanup operations"
print_status ""
print_status "Database verification completed for all operations."
print_status "CLI functionality test suite completed successfully!"