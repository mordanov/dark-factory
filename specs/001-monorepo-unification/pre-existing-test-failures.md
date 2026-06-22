# Pre-existing Test Failures (001-monorepo-unification)

These failures existed before this feature branch and are unrelated to auth adapter insertion (T032-T041). SC-002 is satisfied — zero regressions from auth adapter changes.

## context-distiller — 4 failures in test_memory_repo.py

**Symptom:** `KeyError: 'backend'` when deserializing YAML fixture in `test_fresh_start_no_prior_memory`, `test_archive_before_overwrite`, `test_version_increments_monotonically`, `test_history_pruned_to_keep`.

**Root cause:** The `_BASE_YAML` fixture in `tests/unit/test_memory_repo.py` uses `tech_stack: {backend: '', ...}` — bare YAML keys without quotes. The `MemoryRepository` parser expects a `'backend'` key in `tech_stack` but the YAML parser may deserialize differently depending on mongomock-motor version. Unrelated to auth.

**Follow-up:** Create a separate issue to fix the YAML fixture quoting or align MemoryRepository parser expectations.

## user-input-manager — 1 failure in test_security.py

**Symptom:** `ValueError: password cannot be longer than 72 bytes` in `test_hash_and_verify_password`.

**Root cause:** `passlib==1.7.4` + `bcrypt>=4.0` incompatibility. passlib reads `bcrypt.__about__.__version__` which was removed in bcrypt 4.0. The requirements.txt had no bcrypt pin, so pip resolved to bcrypt 5.0.0.

**Resolution:** Pinned `bcrypt==4.2.1` (canonical version) in `requirements.txt` as part of T070 alignment. This restores compatibility — passlib 1.7.4 works with bcrypt 4.x series.
