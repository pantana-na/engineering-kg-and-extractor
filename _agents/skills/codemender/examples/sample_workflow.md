# End-to-End CodeMender Security Orchestration Walkthrough

This guide demonstrates a complete orchestration run through all 3 stages of CodeMender.

---

## 1. Discovery Stage (`cm find`)

Scan the target repository or module:
```bash
export GOOGLE_CLOUD_PROJECT=your-gcp-project-id
cm find ./src -y --bypass-warning
```

Output:
```text
🔒 Found 2 vulnerabilities:

ID        SEVERITY    TYPE               FILE           TITLE
────────  ────────    ────               ────           ─────
a1b2c3d4  🔴 CRITICAL  SQL Injection      db/users.py    SQL Injection in getUserById
e5f6g7h8  🔴 CRITICAL  Command Injection  api/backup.py  OS Command Injection in execBackup
```

Generated Report: `docs/codemender-01-vulnerability-scan-report.md`

---

## 2. Verification Stage (`cm verify`)

Verify exploitability of finding `a1b2c3d4` inside the isolated sandbox:
```bash
cm verify a1b2c3d4 -y --bypass-warning
```

Output:
```text
🔬 Executing sandbox PoC exploit...
✅ Vulnerability confirmed exploitable (True Positive).
```

Generated Report: `docs/codemender-02-verification-a1b2c3d4-report.md`

---

## 3. Remediation Stage (`cm fix`)

Generate and apply automated patch:
```bash
cm fix a1b2c3d4 -y --bypass-warning
```

Output:
```diff
--- a/db/users.py
+++ b/db/users.py
@@ -14,3 +14,3 @@
-    cursor.execute(f"SELECT * FROM users WHERE id = '{user_id}'")
+    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

Generated Report: `docs/codemender-03-remediation-a1b2c3d4-report.md`
