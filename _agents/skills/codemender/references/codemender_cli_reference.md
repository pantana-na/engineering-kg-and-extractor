# CodeMender CLI & Architecture Reference Guide

CodeMender is Google Cloud's AI code security agent that finds, verifies, and remediates deep security vulnerabilities across multi-language codebases.

---

## 1. System Architecture & Components

CodeMender consists of two tightly integrated components:

```mermaid
flowchart TD
    subgraph Local Workstation / Environment
        CLI["CodeMender CLI (cm)"]
        Sandbox["OS-Level Sandbox (Linux namespaces / Seatbelt)"]
        VCS["Version Control (Git)"]
        StateDB[("State DB (~/.codemender/state.db)")]
        CLI <--> Sandbox
        CLI <--> VCS
        CLI <--> StateDB
    end

    subgraph Google Cloud (Vertex AI)
        API["https://aiplatform.googleapis.com"]
        RE["Cloud Reasoning Engine / Agents"]
        Models["Gemini 3.7 Flash / Gemini 3.1 Pro"]
        API <--> RE
        RE <--> Models
    end

    CLI <-->|"REST / SSE (StartSession, WaitOperation)"| API
```

1. **Cloud-Hosted Reasoning Engine (Vertex AI)**:
   - High-reasoning agent orchestration powered by fine-tuned Gemini models with Google DeepMind security skills.
   - Evaluates abstract syntax trees (ASTs), data flow graphs, taint flows, and multi-file call stacks.
2. **Local Client Worker Daemon (`cm`)**:
   - Thin, secure worker executing local read/write/command tools on demand within an OS-level sandbox container (`exebox`).

---

## 2. Command Reference

### Workspace & Setup Commands
| Command | Description | Key Flags |
| :--- | :--- | :--- |
| `cm init` | Initialize local workspace and config (`~/.codemender/config.yaml`) | `--verify` |
| `cm update` | Update CodeMender CLI binary to latest release | `-y` |
| `cm clean` | Clean up findings cache, temporary logs, and reports | |

### Core Security Lifecycle Commands
| Lifecycle Stage | Command | Description | Key Flags |
| :--- | :--- | :--- | :--- |
| **1. Discovery** | `cm find <path>` | Scans directory or file for software weaknesses | `-y`, `--model`, `-c <context>`, `--bypass-warning` |
| **2. Verification** | `cm verify <finding-id>` | Synthesizes and runs isolated PoC exploit to triage issue | `-y`, `-c <context>`, `--skip-exploit-verification`, `--sandbox` |
| **3. Remediation** | `cm fix <finding-id>` | Refactors code, generates patch, and runs tests | `-y`, `--bypass-warning`, `--model`, `-c <context>` |
| **Reporting** | `cm report` | Lists active, open, and fixed security findings | `-y` |
| **Session Control**| `cm session [list\|resume\|cancel]` | Manages active or interrupted scan/fix sessions | |

---

## 3. Configuration Parameters (`config.yaml`)

Configuration file location: `~/.codemender/config.yaml` or `<workspace>/.codemender/config.yaml`.

```yaml
build:
  command: make build && make test  # Command used by agent to verify patches against tests
scan:
  extensions:
    include:
      - .py
      - .java
      - .go
      - .js
      - .ts
      - .c
      - .cc
      - .cpp
      - .h
      - .rb
      - .php
    exclude:
      - .min.js
      - .generated.go
      - .pb.go
  incremental: true
  max_file_size_kb: 500
tools:
  confirm_commands: true   # Set to false (-y) for automated pipelines
  confirm_writes: true     # Set to false (-y) to allow automated patch writes
sandbox:
  enabled: true
  mounts:
    target_dir: "."
  network:
    profile: "permissive-closed"  # Options: permissive-closed (isolated), permissive-open
security:
  protected_files:
    - "~/.ssh/*"
vcs:
  type: git                # Supports git or mercurial
```

---

## 4. Troubleshooting & Best Practices

1. **403 Forbidden / SECURITY_POLICY_VIOLATED**:
   - Cause: Target project is in a VPC Service Controls (VPC-SC) perimeter blocking `aiplatform.googleapis.com`.
   - Resolution: Configure VPC-SC Ingress Rule or Access Level in Access Context Manager.
2. **Missing Git Repository Error (Exit code 128)**:
   - Cause: CodeMender requires a Git repository to manage state and rollbacks.
   - Resolution: Run `git init && git add . && git commit -m "init"` before scanning.
3. **Responsibility Warning Bypass**:
   - Pass `--bypass-warning` when running non-interactive automated workflows.
