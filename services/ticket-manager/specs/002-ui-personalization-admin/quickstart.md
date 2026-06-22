# Quickstart & Test Scenarios: UI Personalization & Admin Management

**Branch**: `002-ui-personalization-admin` | **Date**: 2026-05-24

---

## Prerequisites

- Existing ticket-manager stack running locally (backend on :8000, frontend on :5173)
- At least one `administrator` account and one `user` account in the database
- `i18next` and `react-i18next` installed in `frontend/`
- Feature branch `002-ui-personalization-admin` checked out

---

## Scenario 1: Language Switching

**Goal**: Verify language switching works end-to-end and persists.

```
1. Open http://localhost:5173 — app loads in English (default)
2. Locate the language switcher in the header (shows "EN")
3. Click and select "Русский (RU)"
   → All visible labels immediately switch to Russian (no page reload)
   → Switcher now shows "RU"
4. Refresh the page
   → App reloads still in Russian
5. Navigate to a project page, then ticket detail
   → Russian is consistent across all pages
6. Switch to "Español (ES)"
   → Spanish labels visible
7. Close the browser tab, reopen http://localhost:5173
   → Spanish is still active
8. Open browser DevTools → Application → Local Storage → localhost:5173
   → Key "lang" = "es"
9. Switch back to "English (EN)" — UI returns to English
```

---

## Scenario 2: Color Theme Selection

**Goal**: Verify all 6 themes apply, persist, and pass visual contrast check.

```
1. Open the user profile menu (top-right of header)
2. Locate the theme selector showing 6 options
3. Click "Dark"
   → Interface immediately switches to dark colour scheme
   → No page reload required; change takes effect in < 300ms
4. Refresh the page
   → Dark theme is still applied
5. Cycle through all 6 themes: Light, Dark, Solarized, Oceanic, High Contrast, Warm
   → Each applies immediately and consistently across header, cards, buttons, forms
6. Select "High Contrast" (black/white)
   → Interface is pure greyscale
   → All text is clearly readable (verify contrast visually)
7. Close browser, reopen app
   → High Contrast theme is restored
8. Open DevTools → Local Storage → Key "theme" = "high-contrast"
```

---

## Scenario 3: Persistent URL Navigation

**Goal**: Verify board/list views have stable URLs and ticket detail persists on refresh.

```
1. Navigate to a project: http://localhost:5173/projects/{projectId}
   → Default view loads (list)
   → URL shows /projects/{projectId}?view=list (or no param → defaults to list)

2. Click "⊞ Board" toggle
   → Board view is displayed
   → URL updates to /projects/{projectId}?view=board

3. Refresh the page
   → Board view is still shown (NOT reset to list)

4. Copy the URL, open in a new tab
   → New tab loads the board view directly

5. Click "☰ List" toggle
   → List view shown
   → URL updates to /projects/{projectId}?view=list

6. Use browser back button
   → Board view is restored (URL reverts to ?view=board)

7. Open a ticket → navigate to /tickets/{ticketId}
   → Ticket detail page loads

8. Refresh the ticket detail page
   → Same ticket detail loads (not redirected to project list)

9. Directly paste /tickets/{ticketId} in address bar
   → Ticket detail loads for an authenticated user
```

---

## Scenario 4: Admin User Management (Happy Path)

**Goal**: Full create → edit → block → unblock lifecycle.

```
1. Log in as administrator
2. Navigate to http://localhost:5173/admin/users
   → User management page loads with full user table
   → Non-admin users navigating here are redirected to /projects

3. CREATE USER:
   Click "+ New User"
   Fill in: email = newuser@example.com, password = "Password123", role = user
   Click "Create"
   → New user appears in the table with status "Active"
   → Log in as newuser@example.com in another browser / incognito
     → Login succeeds

4. EDIT USER:
   Click "Edit" on newuser@example.com
   Change email to updated@example.com
   Click "Save"
   → Row updates to show updated@example.com

5. BLOCK USER:
   Click "Block" on updated@example.com
   → Status column changes to "Blocked"
   → In the other browser: log out, attempt to log back in
     → Login rejected with "Your account has been blocked" message

6. UNBLOCK USER:
   Click "Unblock" on updated@example.com
   → Status column changes to "Active"
   → In the other browser: login attempt now succeeds

7. SELF-PROTECTION:
   Locate the admin's own row in the table
   → "Block" action is absent or disabled for own account
   → Attempting to call POST /api/v1/admin/users/{ownId}/block returns 403
```

---

## Scenario 5: Blocked User Login Enforcement

**Goal**: Confirm backend blocks login, not just frontend.

```
# Using curl or httpie:
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"blocked@example.com","password":"correctpassword"}'

# Expected response:
HTTP 403
{"detail": "Your account has been blocked. Contact an administrator."}
```

---

## API Smoke Tests

```bash
# Authenticated as admin — list all users
curl -H "Authorization: Bearer {token}" http://localhost:8000/api/v1/admin/users
# → 200, JSON array with blocked_at field

# Authenticated as regular user — should fail
curl -H "Authorization: Bearer {user_token}" http://localhost:8000/api/v1/admin/users
# → 403 Forbidden

# Unauthenticated
curl http://localhost:8000/api/v1/admin/users
# → 403 Forbidden
```
