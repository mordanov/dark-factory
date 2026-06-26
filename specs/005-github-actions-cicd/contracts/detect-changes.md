# Contract: .github/scripts/detect-changes.sh

**Type**: Shell script
**Invoked by**: `ci-cd.yml` validate job

## Inputs

- Git context: must be invoked inside a git repository with at least one prior commit
- `$1` (optional): base commit SHA (defaults to `HEAD^` if not provided)

## Outputs

Writes to stdout: a JSON array of service name strings.

```
["tm-backend", "uim-frontend"]
```

Special cases:
- Empty array `[]` — no services changed (documentation-only push)
- All services — when `infra/docker-compose.yml` is in the diff

## Behaviour

1. Computes `git diff --name-only HEAD^ HEAD` (or base vs HEAD)
2. Maps each changed path to zero or more service names using the ServiceMap
3. If `infra/docker-compose.yml` appears: returns ALL service names
4. Deduplicates and emits as compact JSON array
5. Exits 0 always (even on empty set)

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (may be empty array) |
| 1 | Git not available or not in a repo |

## Example Invocations

```bash
# Standard — compare last commit
.github/scripts/detect-changes.sh
# Output: ["orchestrator"]

# Full rebuild trigger
echo "infra/docker-compose.yml changed in commit"
# Output: ["uim-backend","tm-backend","orchestrator","context-distiller","agent-dispatcher","agent-tools","uim-frontend","tm-frontend","nginx"]

# Documentation-only commit
# Output: []
```
