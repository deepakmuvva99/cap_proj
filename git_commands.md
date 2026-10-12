# Enterprise Git Workflow & Team Collaboration Guide
## Project: AI Invoice Auditor (Multi-Service Agentic Platform)

This document establishes the enterprise Git strategy for a 4-person engineering team. It specifies explicit file ownership, branch naming standards, commit message conventions, and exact command sequences for each member.

---

## 1. Team Structure & File Ownership Matrix

To eliminate merge conflicts and maintain organizational accountability, file ownership is strictly partitioned across the 4 roles:

```
+-----------------------------------------------------------------------------------------------+
| ROLE                     | ASSIGNED RESPONSIBILITY           | EXCLUSIVE FILE OWNERSHIP       |
+--------------------------+-----------------------------------+--------------------------------+
| 1. Maintainer (Lead)     | DevOps, Orchestration, Docs,      | compose.yaml                   |
|                          | Repository Policies & Releases    | docker-compose.yml             |
|                          |                                   | .env.example, .gitignore       |
|                          |                                   | README.md, slides.md           |
|                          |                                   | knowledge.txt, explanation.md  |
+--------------------------+-----------------------------------+--------------------------------+
| 2. Developer 1           | Database Infrastructure &         | db/init.sql                    |
|    (Data / Backend)      | Mock ERP Microservice             | db/erp_schema.sql              |
|                          |                                   | db/audit_schema.sql            |
|                          |                                   | mock_erp/Dockerfile            |
|                          |                                   | mock_erp/requirements.txt      |
|                          |                                   | mock_erp/.dockerignore         |
|                          |                                   | mock_erp/app/*                 |
|                          |                                   | data/ERP_mockdata/*            |
+--------------------------+-----------------------------------+--------------------------------+
| 3. Developer 2           | LangGraph Audit Engine,           | config/rules.yaml              |
|    (Agent / Extraction)  | File Routing & Ingestion,         | config/personas.yaml           |
|                          | Data & Business Validation Nodes  | agent/Dockerfile               |
|                          |                                   | agent/requirements.txt         |
|                          |                                   | agent/.dockerignore            |
|                          |                                   | agent/app/main.py              |
|                          |                                   | agent/app/config.py            |
|                          |                                   | agent/app/db.py                |
|                          |                                   | agent/app/cache.py             |
|                          |                                   | agent/app/extractors/*         |
|                          |                                   | agent/app/workflow/*           |
|                          |                                   | tests/test_extraction.py       |
|                          |                                   | tests/test_validation.py       |
+--------------------------+-----------------------------------+--------------------------------+
| 4. Developer 3           | RAG Engine (Qdrant),              | agent/app/llm/*                |
|    (RAG / Frontend)      | AWS Bedrock Integration,          | agent/app/rag/*                |
|                          | RAG Triad Reflection,             | streamlit_ui/Dockerfile        |
|                          | Streamlit Auditor Dashboard       | streamlit_ui/requirements.txt  |
|                          |                                   | streamlit_ui/.dockerignore     |
|                          |                                   | streamlit_ui/app/*             |
|                          |                                   | tests/test_rag.py              |
+--------------------------+-----------------------------------+--------------------------------+
```

---

## 2. Branching Strategy & Conventions

* **`main`**: Production branch. Locked. Merges only through approved Pull Requests.
* **`develop`**: Integration branch where all feature branches converge.
* **Feature Branches**: Formatted as `feature/<member>-<feature-name>`:
  * `feature/dev1-erp-and-database`
  * `feature/dev2-agent-workflow`
  * `feature/dev3-rag-and-ui`
* **Release Branch**: `release/v1.0.0` for final smoke testing before tagging `main`.

---

## 3. Step-by-Step Command Sequences per Team Member

### 👤 MEMBER 1: Maintainer / Team Lead (Repo Setup & Governance)

#### Phase 1: Initialize Git Repository & Scaffold Project
Run in terminal:
```bash
# 1. Initialize git in workspace
git init

# 2. Add remote repository (replace with your GitHub/GitLab URL)
git remote add origin https://github.com/your-org/ai-invoice-auditor.git

# 3. Add base configuration, ignore rules, and root compose files
git add .gitignore .env.example compose.yaml docker-compose.yml
git add README.md slides.md knowledge.txt explanation.md git_commands.md

# 4. Commit repository foundation
git commit -m "chore(init): initialize project structure and multi-service compose orchestration"

# 5. Set main branch and push
git branch -M main
git push -u origin main

# 6. Create and publish develop branch
git checkout -b develop
git push -u origin develop
```

#### Phase 2: Reviewing PRs, Merging, and Tagging Release
```bash
# Fetch all remote branches
git fetch origin

# Review Developer branches locally if needed
git checkout feature/dev1-erp-and-database
git log --oneline -n 5

# Switch to develop to merge approved work
git checkout develop
git pull origin develop

# Merge features with merge commit
git merge --no-ff feature/dev1-erp-and-database -m "merge: incorporate ERP service and PostgreSQL schemas"
git merge --no-ff feature/dev2-agent-workflow -m "merge: incorporate LangGraph audit workflow and extractors"
git merge --no-ff feature/dev3-rag-and-ui -m "merge: incorporate Bedrock RAG pipeline and Streamlit UI"
git push origin develop

# Create Release branch and tag on main
git checkout main
git pull origin main
git merge --no-ff develop -m "release: v1.0.0 containerized AI invoice auditor"
git tag -a v1.0.0 -m "Release v1.0.0 - Passed all 6 Verification Checks"
git push origin main --tags
```

---

### 👤 MEMBER 2: Developer 1 (Database & Mock ERP Microservice)

#### Phase 1: Clone & Create Feature Branch
```bash
# 1. Clone repository
git clone https://github.com/your-org/ai-invoice-auditor.git
cd ai-invoice-auditor

# 2. Checkout develop and branch off
git checkout develop
git pull origin develop
git checkout -b feature/dev1-erp-and-database
```

#### Phase 2: Work & Commit Assigned Files
```bash
# Check status of your assigned files
git status

# Stage database schemas and ERP mock data
git add db/init.sql db/erp_schema.sql db/audit_schema.sql
git add data/ERP_mockdata/
git commit -m "feat(db): implement 3-schema PostgreSQL architecture and seed master data"

# Stage mock-erp service files
git add mock_erp/Dockerfile mock_erp/requirements.txt mock_erp/.dockerignore
git add mock_erp/app/main.py mock_erp/app/database.py mock_erp/app/models.py mock_erp/app/__init__.py
git commit -m "feat(erp): build isolated Mock ERP FastAPI microservice on port 8000"

# Push feature branch to remote
git push -u origin feature/dev1-erp-and-database
```

---

### 👤 MEMBER 3: Developer 2 (LangGraph Agent, Extraction & Validation)

#### Phase 1: Clone & Create Feature Branch
```bash
# 1. Clone repository
git clone https://github.com/your-org/ai-invoice-auditor.git
cd ai-invoice-auditor

# 2. Checkout develop and branch off
git checkout develop
git pull origin develop
git checkout -b feature/dev2-agent-workflow
```

#### Phase 2: Work & Commit Assigned Files
```bash
# Stage validation rules and persona prompts
git add config/rules.yaml config/personas.yaml
git commit -m "feat(rules): define audit tolerances, currency constraints, and agent personas"

# Stage document extraction engine (PDF, DOCX, OCR)
git add agent/app/extractors/
git add tests/test_extraction.py
git commit -m "feat(extractors): implement multi-format router with pdfplumber and Tesseract OCR fallback"

# Stage LangGraph workflow nodes and state
git add agent/app/workflow/
git add agent/app/config.py agent/app/db.py agent/app/cache.py agent/app/main.py
git add agent/Dockerfile agent/requirements.txt agent/.dockerignore
git add tests/test_validation.py
git commit -m "feat(agent): construct LangGraph audit workflow and reporting engine"

# Push feature branch to remote
git push -u origin feature/dev2-agent-workflow
```

---

### 👤 MEMBER 4: Developer 3 (Bedrock LLM, RAG Pipeline & Streamlit UI)

#### Phase 1: Clone & Create Feature Branch
```bash
# 1. Clone repository
git clone https://github.com/your-org/ai-invoice-auditor.git
cd ai-invoice-auditor

# 2. Checkout develop and branch off
git checkout develop
git pull origin develop
git checkout -b feature/dev3-rag-and-ui
```

#### Phase 2: Work & Commit Assigned Files
```bash
# Stage AWS Bedrock integration and RAG reflection engine
git add agent/app/llm/
git add agent/app/rag/
git add tests/test_rag.py
git commit -m "feat(rag): implement Qdrant vector indexing and RAG Triad reflection graph"

# Stage Streamlit Auditor Dashboard
git add streamlit_ui/Dockerfile streamlit_ui/requirements.txt streamlit_ui/.dockerignore
git add streamlit_ui/app/main.py streamlit_ui/app/db.py streamlit_ui/app/api_client.py streamlit_ui/app/__init__.py
git commit -m "feat(ui): build 5-tab Streamlit dashboard with HIL feedback and revalidation"

# Push feature branch to remote
git push -u origin feature/dev3-rag-and-ui
```

---

## 4. Pull Request (PR) & Code Review Guidelines

When each developer finishes their assigned feature branch:
1. Open a Pull Request from `feature/...` into `develop`.
2. Title format: `feat(<component>): brief description`
   - Example: `feat(rag): implement Qdrant indexing and RAG Triad reflection`
3. Description Checklist:
   - [x] Tested locally without errors.
   - [x] No secrets or `.env` files staged.
   - [x] Dockerfile builds with pinned `python:3.11-slim` base image.
   - [x] Non-root user specified (`USER appuser`).
4. **Maintainer Approval:** The Maintainer tests the integration and merges into `develop`.

---

## 5. Daily Synchronization Command Cheat Sheet

Keep your local branch synced with the team:
```bash
# 1. Save current work safely if unfinished
git stash

# 2. Switch to develop and pull latest team updates
git checkout develop
git pull origin develop

# 3. Switch back to your feature branch and rebase
git checkout feature/your-feature-branch
git rebase develop

# 4. Restore stashed work
git stash pop
```
