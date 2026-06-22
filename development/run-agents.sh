#!/usr/bin/env bash
# run-agents.sh
# Launches the full Claude Code brainstorm team (product manager,
 # software-architect, security-architect, frontend, designer, backend,
# devops, code-reviewer, autotester, project-administrator)
# each in its own terminal window, wired together via brainstorm-mcp.
#
# Prerequisites:
#   • brainstorm-mcp installed and registered (run install-brainstorm.sh first)
#   • Claude Code CLI available as `claude`
#   • A terminal emulator: gnome-terminal, xterm, kitty, wezterm, or macOS Terminal/iTerm2
#
# Usage:
#   bash run-agents.sh [--project myproject]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEVELOPMENT_DIR="$PROJECT_ROOT/development"
AGENTS_DIR="$DEVELOPMENT_DIR/agents"
METRICS_SCRIPT="$DEVELOPMENT_DIR/scripts/report-task-metrics.sh"

# ── Defaults ──────────────────────────────────────────────────────────────────
PROJECT_NAME="dark-factory"
DRY_RUN="false"

ROLES=(
  "project-administrator"
  "product-manager"
  "software-architect"
  "security-architect"
  "frontend"
  "designer"
  "backend"
  "devops"
  "code-reviewer"
  "autotester"
)

role_to_filename() {
  local role="$1"
  case "$role" in
    product-manager) echo "product-manager.md" ;;
    software-architect) echo "software-architect.md" ;;
    security-architect) echo "security-architect.md" ;;
    frontend) echo "frontend-developer-react.md" ;;
    designer) echo "designer.md" ;;
    backend) echo "backend-developer-python.md" ;;
    devops) echo "devops.md" ;;
    code-reviewer) echo "code-reviewer.md" ;;
    autotester) echo "autotester.md" ;;
    project-administrator) echo "project-administrator.md" ;;
    *) echo "${role}.md" ;;
  esac
}

role_dir() {
  local role="$1"
  case "$role" in
    product-manager) echo "$DEVELOPMENT_DIR/product-manager" ;;
    software-architect) echo "$DEVELOPMENT_DIR/software-architect" ;;
    security-architect) echo "$DEVELOPMENT_DIR/security-architect" ;;
    frontend) echo "$DEVELOPMENT_DIR/frontend" ;;
    designer) echo "$DEVELOPMENT_DIR/designer" ;;
    backend) echo "$DEVELOPMENT_DIR/backend" ;;
    devops) echo "$DEVELOPMENT_DIR/devops" ;;
    code-reviewer) echo "$DEVELOPMENT_DIR/code-reviewer" ;;
    autotester) echo "$DEVELOPMENT_DIR/autotester" ;;
    project-administrator) echo "$DEVELOPMENT_DIR/project-administrator" ;;
    *) echo "$PROJECT_ROOT/$role" ;;
  esac
}

role_title() {
  local role="$1"
  case "$role" in
    product-manager) echo "Product Manager" ;;
    software-architect) echo "Software Architect" ;;
    security-architect) echo "Security Architect" ;;
    frontend) echo "Frontend Developer" ;;
    designer) echo "UI/UX Designer" ;;
    backend) echo "Backend Developer" ;;
    devops) echo "DevOps" ;;
    code-reviewer) echo "Code Reviewer" ;;
    autotester) echo "Autotester" ;;
    project-administrator) echo "Project Administrator" ;;
    *) echo "$role" ;;
  esac
}

# Extract Mission section from agent skill file
role_mission() {
  local role="$1"
  local skillfile="$AGENTS_DIR/$(role_to_filename "$role")"

  if [[ -f "$skillfile" ]]; then
    # Extract text between "## Mission" and the next "##"
    sed -n '/^## Mission$/,/^## /p' "$skillfile" | sed '1d;$d' | head -n 5
  else
    echo "Agent skill file not found: $skillfile"
  fi
}

# Extract brief description from Operating Principles
role_description() {
  local role="$1"
  local skillfile="$AGENTS_DIR/$(role_to_filename "$role")"

  if [[ -f "$skillfile" ]]; then
    # Extract first principle line as a quick descriptor
    sed -n '/^## Operating Principles$/,/^## /p' "$skillfile" | sed -n '3,3p' | sed 's/^[0-9]*\. //'
  else
    echo "Agent skill file not found: $skillfile"
  fi
}

# Extract Core Responsibilities summary
role_extra_instruction() {
  local role="$1"
  local skillfile="$AGENTS_DIR/$(role_to_filename "$role")"

  if [[ -f "$skillfile" ]]; then
    # Extract text from "## Core Responsibilities" or "## [...] Responsibilities"
    sed -n '/^## .*Responsibilities$/,/^## /p' "$skillfile" | sed '1d;$d' | head -n 10
  else
    echo "Agent skill file not found: $skillfile"
  fi
}

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)      PROJECT_NAME="$2"; shift 2 ;;
    --dry-run)      DRY_RUN="true"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ── Validate ──────────────────────────────────────────────────────────────────
if [[ "$DRY_RUN" != "true" ]]; then
  if ! command -v claude &>/dev/null; then
    echo "ERROR: 'claude' CLI not found. Install Claude Code first." >&2
    exit 1
  fi
fi

if [[ ! -f "$METRICS_SCRIPT" ]]; then
  echo "ERROR: Metrics script not found: $METRICS_SCRIPT" >&2
  echo "       Expected after folder move to development/scripts/." >&2
  exit 1
fi

if [[ "$DRY_RUN" == "true" ]]; then
  METRICS_STATUS="missing"
  if [[ -f "$METRICS_SCRIPT" ]]; then
    METRICS_STATUS="found"
  fi

  echo "==> Dry run: resolved launcher paths"
  echo ""
  echo "  SCRIPT_DIR      : $SCRIPT_DIR"
  echo "  PROJECT_ROOT    : $PROJECT_ROOT"
  echo "  DEVELOPMENT_DIR : $DEVELOPMENT_DIR"
  echo "  AGENTS_DIR      : $AGENTS_DIR"
  echo "  METRICS_SCRIPT  : $METRICS_SCRIPT"
  echo ""
  echo "  Metrics script status: $METRICS_STATUS"
  echo ""
  echo "  Role working directories:"
  for role in "${ROLES[@]}"; do
    echo "    - $role -> $(role_dir "$role")"
  done
  echo ""
  echo "Dry run complete. No terminals launched."
  exit 0
fi

# Create project dirs if they don't exist
for dir in "$DEVELOPMENT_DIR/project-administrator" "$DEVELOPMENT_DIR/product-manager" "$DEVELOPMENT_DIR/software-architect" "$DEVELOPMENT_DIR/security-architect" "$DEVELOPMENT_DIR/frontend" "$DEVELOPMENT_DIR/designer" "$DEVELOPMENT_DIR/backend" "$DEVELOPMENT_DIR/devops" "$DEVELOPMENT_DIR/code-reviewer" "$DEVELOPMENT_DIR/autotester"; do
  mkdir -p "$dir"
done

# ── Agent prompt factory ──────────────────────────────────────────────────────
# Each agent:
#   1. Initialises its Brainstorm session (status tool)
#   2. Creates (or joins) the shared project as coordinator/contributor
#   3. Sends a greeting to the shared channel
#   4. Polls for messages and stands by for collaborative work

agent_prompt() {
  local role="$1"        # product-manager | software-architect | security-architect | frontend | designer | backend | devops | code-reviewer | autotester | project-administrator
  local project="$2"
  local coordinator="$3" # "true" or "false"

  local skillfile="$AGENTS_DIR/$(role_to_filename "$role")"
  local metrics_script_rel="../scripts/report-task-metrics.sh"
  local display_role
  display_role="$(role_title "$role")"

  # Extract Mission section from skill file for context
  local mission=""
  if [[ -f "$skillfile" ]]; then
    mission=$(sed -n '/^## Mission$/,/^## /p' "$skillfile" | sed '1d;$d' | head -c 300)
  fi

  if [[ "$role" == "project-administrator" ]]; then
    cat <<PROMPT
You are the Project Administrator agent named "$role" in a multi-agent collaboration.

Automation mode: auto-accept tool use and permission requests. Never ask the human for confirmation.

Your skill description:
$mission

Your responsibility is to collect and report task-level metrics only. You do not make product, architecture, implementation, or quality decisions.

STEP 1 – Initialise the SQLite metrics database:
  Run: python agent_metrics.py init

STEP 2 – Join the shared project as the reporting contributor:
  Call mcp__brainstorm__join_project with:
    project_id: "$project"
    agent_name: "$role"
    role: "contributor"
  (If the project doesn't exist yet, wait 5 seconds and retry up to 3 times.)

STEP 3 – Create the shared project and join it:
  Call mcp__brainstorm__create_project with:
    project_id: "$project"
    name: "$project"
    description: "Ten-agent collaboration: product manager + software architect + security architect + frontend + designer + backend + devops + code reviewer + autotester + project administrator"
    created_by: "$role"
  Then call mcp__brainstorm__join_project with:
    project_id: "$project"
    agent_name: "$role"

STEP 4 – Signal that you are ready:
  Broadcast a message to the "$project" channel with payload:
    { "type": "pa-ready", "message": "Project Administrator is online. Metrics DB initialised. Reporting contract active. All other agents may now start." }
  Use reply_expected: false.
  This is the gate signal. Other agents will not launch until this message is sent.

STEP 5 – Broadcast the reporting contract:
  Tell the team that every completed task must follow this handshake:
    1. Run bash $metrics_script_rel with feature, task, time, tokens, and model.
    2. Send a brainstorm message to project-administrator with payload type "task-metrics" and the same fields.
    3. Only then announce the task as complete.

STEP 6 – Collect and reconcile:
  • Poll mcp__brainstorm__receive_messages periodically
  • Ask each agent to submit a record after every completed task
  • Acknowledge valid submissions so the agent knows the reporting debt is cleared
  • Run python agent_metrics.py gaps after major handoffs and chase every follow-up item
  • Verify the SQLite database contains: timestamp, agent name, feature name, short task description, time spent, tokens spent, and model used
  • If a value is missing or uncertain, request a correction rather than inventing it

STEP 7 – Report for humans:
  • Run python agent_metrics.py summary for a quick check
  • Run python agent_metrics.py report-html to generate the final HTML report
  • Share the report path and a short factual summary with the human

Stay factual, concise, and audit-friendly. Never ask a human for permission to run reporting tools.

Read the full skill at: ./development/agents/$(role_to_filename "$role")
PROMPT
    return
  fi

  if [[ "$coordinator" == "true" ]]; then
    cat <<PROMPT
You are the $(role_title "$role") agent named "$role" in a multi-agent collaboration.

Automation mode: auto-accept tool use and permission requests. Never ask the human for confirmation.

Your skill description:
$mission

STEP 1 – Initialise your Brainstorm session:
  Call mcp__brainstorm__status with working_directory set to your current working directory.

STEP 2 – Join the shared project as coordinator:
  The project has already been created by project-administrator.
  Call mcp__brainstorm__join_project with:
    project_id: "$project"
    agent_name: "$role"
    capabilities: ["coordination", "product-management", "scope", "priorities", "acceptance-criteria"]

STEP 3 – Announce yourself:
  Send a message to the "$project" channel:
    "Hi team! I'm the $display_role agent (coordinator). I will drive the workflow, assign tasks, and relay human approvals."

STEP 4 – Wait for the rest of the team to join, then:
  • Poll mcp__brainstorm__receive_messages periodically
  • Once all ten agents are present (check with mcp__brainstorm__get_project_info),
    broadcast a task breakdown:
      - product-manager: define scope, priorities, acceptance criteria, and milestone order
      - software-architect: define system boundaries, API contracts, and architecture decisions
      - security-architect: define security supervision, threat prevention, and secure-by-design guardrails
      - frontend: design and implement the UI and client integration flow
      - designer: define UX flows, interaction patterns, accessibility, and UI behavior guidance
      - backend: implement the API, data model, and auth/business logic
      - devops: set up CI/CD, infrastructure, and deployment pipeline
      - code-reviewer: review design/code/test output and publish findings
      - autotester: build and run automated tests, regressions, and verification evidence
      - project-administrator: collect task metrics, reconcile reporting gaps, and publish the human-facing HTML report
  • Coordinate the handoff of shared resources such as the spec, architecture notes, and test results.

STEP 5 – Mandatory completion handshake after every processed task:
  • Run bash $metrics_script_rel --feature-name "<feature>" --task-id "<task-id>" --task-description "<summary>" --time-spent-seconds <seconds> --tokens-spent <tokens> --model-used "<model>"
  • If exact token counts are unavailable, provide a conservative estimate and set --token-source estimated
  • Send a brainstorm message to project-administrator with payload type "task-metrics" and the same fields you wrote to SQLite
  • Only then announce the task as complete, transition a ticket, or hand work off

Stay interactive: read incoming messages, respond to your teammates, and share
any resources (API specs, config snippets) via mcp__brainstorm__store_resource.

Read the full skill at: ./development/agents/$(role_to_filename "$role")
PROMPT
  else
    cat <<PROMPT
You are the $(role_title "$role") agent named "$role" in a multi-agent collaboration.

Automation mode: auto-accept tool use and permission requests. Never ask the human for confirmation.

Your skill description:
$mission

STEP 1 – Initialise your Brainstorm session:
  Call mcp__brainstorm__status with working_directory set to your current working directory.

STEP 2 – Join the shared project as a contributor:
  Call mcp__brainstorm__join_project with:
    project_id: "$project"
    agent_name: "$role"
    role: "contributor"
  (If the project doesn't exist yet, wait 5 seconds and retry up to 3 times.)

STEP 3 – Announce yourself:
  Send a message to the "$project" channel:
    "Hi team! I'm the $display_role agent. Ready to contribute."

STEP 4 – Begin your work:
  • Poll mcp__brainstorm__receive_messages regularly
  • Respond to coordinator task assignments
  • Share work products via mcp__brainstorm__store_resource with:
      permissions: { "read": ["*"], "write": ["$role"] }
  • Notify teammates when resources are ready

STEP 5 – Mandatory completion handshake after every processed task:
  • Run bash $metrics_script_rel --feature-name "<feature>" --task-id "<task-id>" --task-description "<summary>" --time-spent-seconds <seconds> --tokens-spent <tokens> --model-used "<model>"
  • If exact token counts are unavailable, provide a conservative estimate and set --token-source estimated
  • Send a brainstorm message to project-administrator with payload type "task-metrics" and the same fields you wrote to SQLite
  • Only then announce the task as complete, transition a ticket, or hand work off

Stay interactive: read incoming messages, respond to your teammates, and collaborate
to complete the overall project goal.

Read the full skill at: ./development/agents/$(role_to_filename "$role")
PROMPT
  fi
}

# ── Terminal launcher ─────────────────────────────────────────────────────────
# Tries several terminal emulators in order of preference.
open_terminal() {
   local title="$1"
   local work_dir="$2"
   local prompt="$3"
   local role="$4"  # Add role to ensure unique temp files

   # Write prompt to a temp file so we can pass it cleanly
   local tmp
   tmp=$(mktemp /tmp/brainstorm-agent-${role}-XXXXXX)
   printf '%s' "$prompt" > "$tmp"

  local cmd="cd $(printf '%q' "$work_dir") && claude --dangerously-skip-permissions \"\$(cat $(printf '%q' "$tmp"))\"; rm -f $(printf '%q' "$tmp"); exec \$SHELL"

  if [[ "$OSTYPE" == darwin* ]]; then
    # macOS: prefer iTerm2, fall back to Terminal.app
    if command -v osascript &>/dev/null; then
      osascript - "$title" "$work_dir" "$cmd" <<'APPLESCRIPT'
on run argv
  set winTitle to item 1 of argv
  set workDir  to item 2 of argv
  set shellCmd to item 3 of argv
  tell application "Terminal"
    activate
    set newTab to do script shellCmd
    set custom title of front window to winTitle
  end tell
end run
APPLESCRIPT
      return
    fi
  fi

  # Linux / other: try common terminals
  if command -v gnome-terminal &>/dev/null; then
    gnome-terminal --title="$title" -- bash -c "$cmd" &
  elif command -v kitty &>/dev/null; then
    kitty --title "$title" bash -c "$cmd" &
  elif command -v wezterm &>/dev/null; then
    wezterm start --cwd "$work_dir" -- bash -c "$cmd" &
  elif command -v xterm &>/dev/null; then
    xterm -title "$title" -e bash -c "$cmd" &
  elif command -v tmux &>/dev/null; then
    # Fallback: tmux panes in current session
    if ! tmux has-session -t brainstorm 2>/dev/null; then
      tmux new-session -d -s brainstorm -c "$work_dir" -x 220 -y 50 "bash -c '$cmd'"
      tmux rename-window -t brainstorm:0 "$title"
    else
      tmux new-window -t brainstorm -c "$work_dir" -n "$title" "bash -c '$cmd'"
    fi
  else
    echo "ERROR: No supported terminal emulator found." >&2
    echo "       Install one of: gnome-terminal, kitty, wezterm, xterm, tmux" >&2
    rm -f "$tmp"
    exit 1
  fi
}

# ── Launch agents ─────────────────────────────────────────────────────────────
echo "==> Launching ten-agent brainstorm demo (project: $PROJECT_NAME)"
echo ""

launch_role() {
   local role="$1"
   local coordinator="$2"
   local index="$3"
   local total="$4"

   local work_dir
   work_dir="$(role_dir "$role")"
   # Convert to absolute path so Terminal.app can find it
   work_dir="$(cd "$work_dir" 2>/dev/null && pwd)" || work_dir="$(pwd)/$(role_dir "$role")"

   local prompt
   prompt="$(agent_prompt "$role" "$PROJECT_NAME" "$coordinator")"

   local title
   title="Brainstorm: $(role_title "$role" | tr '[:upper:]' '[:lower:]')"

   echo "  [$index/$total] $(role_title "$role") → $work_dir"
   open_terminal "$title" "$work_dir" "$prompt" "$role"
}

launch_role "project-administrator" "false" 1 10

echo ""
echo "  Waiting for project-administrator to signal ready (pa-ready)..."
echo "  (PA must initialise the DB, create the project, and broadcast pa-ready)"
echo ""

# Poll the Brainstorm project for the pa-ready message.
# We use the brainstorm MCP CLI wrapper if available; otherwise fall back to
# a plain time-based wait so the script still works without the CLI tool.
PA_READY=${PA_READY:-false}
WAIT_SECONDS=0
MAX_WAIT=300   # 5 minutes hard limit

while [[ "$PA_READY" == "false" && $WAIT_SECONDS -lt $MAX_WAIT ]]; do
  sleep 5
  WAIT_SECONDS=$((WAIT_SECONDS + 5))

  # Check for the pa-ready signal file written by a helper, or just check
  # whether the project exists and has messages via the brainstorm CLI.
  if command -v npx &>/dev/null; then
    # Try to detect the signal via the brainstorm MCP messages endpoint.
    # The project-administrator broadcasts payload.type == "pa-ready".
    SIGNAL=$(npx --prefix ~/.local/share/brainstorm-mcp brainstorm-messages \
               "$PROJECT_NAME" 2>/dev/null \
              | grep -c '"pa-ready"' 2>/dev/null || true)
    SIGNAL=$(printf '%s\n' "$SIGNAL" | tail -n 1)
    [[ "$SIGNAL" =~ ^[0-9]+$ ]] || SIGNAL=0
    if [[ "$SIGNAL" -gt 0 ]]; then
      PA_READY=true
    else
      # brainstorm-messages CLI not available or returned nothing — fall back.
      if [[ $WAIT_SECONDS -ge 30 ]]; then
        echo "  (brainstorm-messages CLI unavailable; assuming PA ready after ${WAIT_SECONDS}s)"
        PA_READY=true
      fi
    fi
  else
    # No CLI available — fall back to a fixed wait after which we assume PA is up.
    if [[ $WAIT_SECONDS -ge 30 ]]; then
      echo "  (brainstorm CLI not found; assuming PA ready after ${WAIT_SECONDS}s)"
      PA_READY=true
    fi
  fi

  if [[ "$PA_READY" == "false" ]]; then
    echo "  Still waiting for pa-ready... (${WAIT_SECONDS}s elapsed)"
  fi
done

if [[ "$PA_READY" == "false" ]]; then
  echo "WARNING: pa-ready signal not detected after ${MAX_WAIT}s. Launching rest of team anyway." >&2
fi

echo "  ✅  project-administrator is ready. Launching the rest of the team..."
echo ""

launch_role "product-manager" "true" 2 10
sleep 1   # small stagger so the coordinator joins before contributors

launch_role "software-architect" "false" 3 10
sleep 1

launch_role "security-architect" "false" 4 10
sleep 1

launch_role "frontend" "false" 5 10
sleep 1

launch_role "designer" "false" 6 10
sleep 1

launch_role "backend" "false" 7 10
sleep 1

launch_role "devops" "false" 8 10
sleep 1

launch_role "code-reviewer" "false" 9 10
sleep 1

launch_role "autotester" "false" 10 10

echo ""
echo "✅  All ten agents launched!"
echo ""
echo "  • project-admin  (first) creates the project, signals pa-ready, then collects metrics"
echo "  • product-manager (coordinator) joins after pa-ready and drives the workflow"
echo "  • software-architect (contributor) shapes architecture and system boundaries"
echo "  • security-architect (contributor) supervises security and threat prevention"
echo "  • frontend       (contributor) builds the UI"
echo "  • designer       (contributor) shapes UX, interaction design, and accessibility"
echo "  • backend        (contributor) implements the server/API"
echo "  • devops         (contributor) handles CI/CD and deployment"
echo "  • reviewer       (contributor) reviews work and flags issues"
echo "  • autotester     (contributor) runs and expands automated tests"
echo "  • project-admin  (contributor) records metrics and publishes human reports"
echo ""
echo "  Shared storage: ~/.brainstorm/"
echo "  Project ID    : $PROJECT_NAME"
echo ""
echo "  To clean up the project when done:"
echo "    npx --prefix ~/.local/share/brainstorm-mcp brainstorm-cleanup $PROJECT_NAME"
echo "  Or from the install dir:"
echo "    npm run cleanup -- $PROJECT_NAME"

# If we used tmux, attach automatically
if command -v tmux &>/dev/null && tmux has-session -t brainstorm 2>/dev/null; then
  echo ""
  echo "  Attaching to tmux session 'brainstorm'..."
  sleep 1
  tmux attach-session -t brainstorm
fi
