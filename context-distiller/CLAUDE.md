<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan at
specs/001-context-distiller-service/plan.md
<!-- SPECKIT END -->

## Project Context

Read .specify/memory/ before any /speckit.* command.

## Sibling Projects

The following sibling projects exist at `../` level.
Read them for integration context. Never go above `../`.

| Project | Path                            | What to read                                      |
|---|---------------------------------|---------------------------------------------------|
| Ticket Manager | `../ticket-manager/`            | README.md, src/ (API contracts, data model)       |
| Prompt Studio | `../user-input-manager/`        | README.md, backend/src/api/, backend/src/schemas/ |
| Orchestrator | `../orchestrator/` | src/schemas/, src/services/fsm/, src/api          |

When implementing any feature that touches these systems,
read the relevant files above before generating code or specs.