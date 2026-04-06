---
name: migrate
description: Test-driven infrastructure migration with acceptance tests and step-by-step execution
inputs: [migration_description, target_state]
outputs: [migration_report]
writes_to: [daily-logs/]
side_effects: [ssh_commands, kubectl_commands, audit_log]
---

# Migrate

Execute an infrastructure migration with pre-defined acceptance tests. Tests are written BEFORE any changes are made. After each migration step, tests are re-run to validate progress. Stops automatically after 3 consecutive failures on the same test.

## Steps

### 1. Document the migration plan

Before any changes, write a brief migration plan:
- **Current state:** What exists now
- **Target state:** What should exist after migration
- **Steps:** Ordered list of actions to take
- **Rollback:** How to undo each step if something goes wrong
- **Risk assessment:** What could break

### 2. Write acceptance tests

Create a bash test script at `/tmp/migrate_tests_<timestamp>.sh` with `test_*` functions that validate the desired end state.

**Test script template:**
```bash
#!/bin/bash
# Migration acceptance tests: <migration description>
# Each test_ function returns 0=pass, nonzero=fail. Stdout captured as detail.

test_service_reachable() {
    curl -sf http://<target>/healthz
}

test_dns_resolves() {
    dig +short <domain> | grep -q '<expected_ip>'
}

test_cert_valid() {
    echo | openssl s_client -connect <host>:443 -servername <domain> 2>/dev/null | openssl x509 -noout -dates 2>/dev/null
}

test_pods_running() {
    ssh root@100.103.248.9 'kubectl get pods -n <namespace> --no-headers | grep -v Running' | wc -l | grep -q '^0$'
}

test_ceph_healthy() {
    ssh root@100.118.169.103 'ceph health' | grep -q HEALTH_OK
}

test_old_resource_removed() {
    # Verify the old resource no longer exists
    ! curl -sf http://<old_target>/healthz
}
```

**Run baseline test (all should fail, confirming tests detect pre-migration state):**
```bash
python3 ~/pureMind/tools/migrate_test_runner.py /tmp/migrate_tests_<timestamp>.sh --json
```

### 3. Execute migration step by step

For each step in the migration plan:

1. **Execute the step** (apply manifest, update DNS, run SQL migration, etc.)
2. **Run the relevant tests:**
```bash
python3 ~/pureMind/tools/migrate_test_runner.py /tmp/migrate_tests_<timestamp>.sh --json
```
3. **Evaluate:** If more tests pass than before, proceed. If a test regresses, investigate before continuing.

### 4. Stop conditions

The test runner automatically stops after 3 consecutive failures on the same test. When this happens:

- **Report what failed and why** (test output is captured)
- **Ask the operator for guidance** before trying more approaches
- Do NOT attempt more than 3 different fixes for the same failing test without operator input

### 5. Final verification

After all migration steps are complete:

```bash
python3 ~/pureMind/tools/migrate_test_runner.py /tmp/migrate_tests_<timestamp>.sh --json
```

**All tests must pass.** If any fail, the migration is not complete.

### 6. Log results

Write migration results to the daily log:
```
## Migration: <description>
**Status:** complete/incomplete
**Tests:** N/N passed
**Steps taken:** <list>
**Duration:** <elapsed>
```

## Test Runner Reference

```bash
# Run all tests
python3 ~/pureMind/tools/migrate_test_runner.py <script> --json

# Run single test
python3 ~/pureMind/tools/migrate_test_runner.py <script> --test test_dns_resolves

# Custom retry limit (default: 3)
python3 ~/pureMind/tools/migrate_test_runner.py <script> --max-retries 5

# Custom timeout per test (default: 30s)
python3 ~/pureMind/tools/migrate_test_runner.py <script> --timeout 60
```

## Constraints

- **Tests FIRST.** Never start migration actions before the test script is written and the baseline run confirms tests detect pre-migration state.
- **No auto-rollback.** Flag rollback needs for operator confirmation. Do not undo changes without explicit approval.
- **All actions logged.** SSH, kubectl, and test runner calls logged to pm_audit via audit integration.
- **Test scripts are temporary** (`/tmp/`) and not committed to the vault.
- **3-failure stop.** If the test runner stops, report the full context and wait for operator guidance.
- Never modify DNS, delete resources, or apply destructive changes without confirming the rollback procedure first.
