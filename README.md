# GapFinder AI

A local, full-stack study diagnosis project: **upload → test → identify gaps → revise → re-test**.

## Run in VS Code

Open this folder in VS Code. In its PowerShell terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open **http://127.0.0.1:8765**. On the prepared computer, `python app.py` also works using the installed Flask/requests and the local `.packages` PDF dependencies.

The included VS Code launch configuration supports F5 after installing Microsoft's Python and Python Debugger extensions and selecting the virtual environment interpreter.

Create a student account, then sign in with your email and password.

1. Sign in and upload your syllabus and notes in **Study materials**.
2. Inspect the topic map and past-paper mappings.
3. Generate a diagnostic in demo mode. Answer some incorrectly to see the weak-topic report.
4. Inspect the feedback, gap report and time-budgeted revision plan.
5. Re-test to update the plan and topic-level progress.
6. Try “Explain photosynthesis” in the study assistant and inspect its source links.

## Enable real AI generation and semantic grading

The app runs without a key in a clearly labeled **source recall demo** mode. Demo generation creates fill-in-the-blank questions from source sentences; grading compares the missing word, and the assistant quotes relevant passages. This is not a substitute for the mandatory generative AI features in a final AI demonstration.

For AI comprehension questions, semantic grading and synthesized explanations, use Groq. If `.env` does not exist yet:

```powershell
Copy-Item .env.example .env
```

For **Groq** (the provider recommended by the assignment), create your own key at https://console.groq.com/keys and edit `.env` locally:

```dotenv
AI_PROVIDER=groq
GROQ_API_KEY=your_actual_groq_key
GROQ_MODEL=openai/gpt-oss-20b
PORT=8765
```

Groq currently lists `openai/gpt-oss-20b` in its [free-plan limits](https://console.groq.com/docs/rate-limits); usage is subject to your account limits. Start with a three-question AI quiz to keep request volume low. The app uses [Groq Chat Completions](https://console.groq.com/docs/api-reference) with JSON output, and sends only the retrieved context and the task. No API key is included in frontend code. Live use requires your own Groq key.

Only Groq is supported. Save your key in `.env`, restart the server, then select **AI comprehension** or **AI explanation**. Retrieved passages and student answers are sent to Groq for AI operations. Never commit `.env` or share keys in chat. Provider failures do not silently fall back to demo grading.

**Live Groq verification passed on 9 November 2026:** authentication/model access, sample question generation with exact citation validation, and answer grading. Automated provider-contract tests also cover malformed citations and provider failures.

## Feature coverage

| Requirement | Implementation |
|---|---|
| PDF/text syllabus, notes, past papers | Upload library, PDF page extraction, section-aware overlapping chunks; 12 MB and 300-page bounds |
| Syllabus topic map | Line/heading parsing with unit hierarchy, source matching, manual topic additions |
| Past-paper topic mapping | BM25 retrieval against topic names, frequency counts, ambiguity flags |
| Diagnostic quiz with citations | Demo cloze or AI short-answer questions; document/page/section evidence |
| Explained answer evaluation | Exact-word demo grading or AI 0 / 0.5 / 1 rubric with explanations and evidence |
| Main diagnosis output | Weak/medium/strong plus untested, latest topic scores, reasons, sample-size confidence |
| Personalized revision plan | Weakness and exam frequency priority, available days/minutes, repeat sessions, completion checks |
| Source-only explanation assistant | Relevant excerpts or AI claims backed by validated source IDs and exact quotations; abstention |
| Progress dashboard | Attempt chart, topic score history, point changes, answer review |
| Login and saved student data | Demo account, registration, hashed passwords, signed sessions, CSRF, SQLite account isolation |
| Retrieval/generation separation | `rag.retrieve` vs `rag.generate`; see in-app How it works and architecture below |

## Architecture and assessment rules

Flask serves a responsive vanilla HTML/CSS/JS interface and authenticated JSON API. SQLite persists one isolated study state per account. Files are extracted into text; original binary uploads are not stored. Prior quiz source snapshots remain available even if a library document is removed. `.env`, database contents and the persistent session signing key are ignored by Git.

1. **Ingestion:** `add_document` extracts PDF page text or UTF-8 text into overlapping chunks (up to 1,120 characters), retaining the file, page and heading. Syllabus lines become topics; unit/chapter/module headings establish parent labels.
2. **Retrieval:** `rag.retrieve` uses BM25 term ranking, selecting up to four source passages. No overlap means no evidence. It searches only the current account's notes. Past-paper mapping uses the same retrieval function against syllabus topic names. There is no vector database requirement; BM25 is the retrieval component of this RAG pipeline.
3. **Generation:** `rag.generate` receives the task and already-retrieved chunks. It cannot search the internet. System instructions treat uploaded content and answers as untrusted data, restrict facts to supplied evidence, and request structured JSON. Questions must include an exact source quote; explanations contain claims with exact quotes. Missing/invented IDs or quotes are rejected before saving.
4. **Evaluation:** Demo uses normalized exact-word matching. AI uses evidence-grounded semantic grading with scores 0, 0.5 or 1. Blank answers get zero. A failed provider request leaves the attempt unsubmitted, allowing retry. Submission is serialized per account and repeat submission is rejected.
5. **Diagnosis:** Each topic's latest assessed quiz gives its current percentage: weak `<50`, medium `50–79`, strong `≥80`. Unassessed topics stay **untested**. Under three questions yields a limited-evidence label. These are assessment signals, not validated psychometric mastery probabilities.
6. **Planning:** Priority = `(100 − score) × (1 + 0.15 × min(exam_frequency, 10))`. Untested topics use a provisional 40 for ordering only. Days rotate through priority order in blocks up to 25 minutes; each day's sum equals the configured budget. New attempts refresh all priorities and reset completion checks. This is a deterministic adaptive scheduler, not an LLM-generated timetable.

## Checks

```powershell
python -m unittest discover -s tests -v
node --check static/app.js
```

Tests use a temporary database, never your study data. They cover PDF/text extraction, unreadable uploads, account isolation, CSRF, retrieval and abstention, quiz answer secrecy, grading, duplicate submissions, persistence, diagnostic improvement, plan budgets, completion checks, supported/unsupported citations and mocked provider failures.

## Limitations and intended scope

- Text-based PDFs are supported; image-only scans need external OCR. Complex PDF tables, multi-column ordering and unusual syllabus formatting may need clean TXT input. Review the extracted topic map and add missing topics.
- BM25 relies on shared words. Synonyms and indirect questions may not match; lexical matches can also be irrelevant. Past-paper frequency is a proxy, not a prediction. Ambiguous mappings are flagged but not manually reassigned in this version.
- Exact quote validation proves provenance, not semantic truth. AI outputs still need human review against evidence. Provider failures show an error instead of saving fabricated results.
- The demo and AI quizzes measure different skills; the dashboard labels assessment modes. Quiz scores are not strictly comparable when topics or difficulty differ.
- The service binds to localhost. Do not expose this development server publicly. Public deployment needs HTTPS, a production server, rate limiting, recovery/email verification, broader privacy controls, monitoring and database migrations. Demo credentials are intentionally public.
- Class analytics, parent access, subject workspaces, reminder delivery and LMS integrations are future scope in the supplied statement and are not implemented.

## Project files

- `app.py`: auth, extraction, API, saved state, diagnosis and planning.
- `rag.py`: lexical retrieval, provider boundary, citation checks and demo generation.
- `static/`: responsive interface, styles and browser interactions.
- `sample-materials/`: test fixtures for syllabus, notes and past-paper uploads.
- `tests/test_app.py`: integration and retrieval tests.
- `.vscode/launch.json`: VS Code debugging entry point.

To use a different local port, set `PORT` in `.env`. Back up `instance/` while the server is stopped to retain users, session signing key, files' extracted text and progress.

## Deploy to Vercel

Import the GitHub repository into Vercel using the Flask framework preset.
Connect a PostgreSQL database, such as Neon, through the Vercel Marketplace.
Configure these Production environment variables before deploying:

- `DATABASE_URL` (or `POSTGRES_URL`): pooled PostgreSQL connection URL.
- `FLASK_SECRET_KEY`: a stable random secret, generated with `python -c "import secrets; print(secrets.token_hex(32))"`.
- `GROQ_API_KEY`: the server-side key for AI generation and explanations.

Open the deployment URL, create a student account, and upload a syllabus and
matching notes. The hosted database starts separately from local SQLite.
Vercel uploads are limited to 4 MB per request in the app. Quiz generation can
fall back to local questions and the assistant can return source passages
during provider interruptions.
