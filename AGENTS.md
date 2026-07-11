# Codex Project Guide: Tutor Recommendation

This file is safe to keep in the public repository. It should describe stable
engineering rules, commands, and privacy boundaries only.

## Privacy Boundary

- Do not store personal resumes, application forms, student profiles, contact
  status, generated Excel files, caches, or current crawl results in tracked
  files.
- Local private context may live in `docs/private/` and `data/private/`; both
  are ignored by Git except `data/private/README.md`.
- If a task depends on current local research state, first check whether
  `docs/private/project-context.local.md` exists and read it locally. Never copy
  its contents into public docs.
- Public docs may explain schemas, commands, and reusable methodology. They
  should not record a specific applicant's profile, finished target counts,
  teacher-level evidence, or contact decisions.

## Collaboration Rule

Before a task, decide whether sub-agents would help:

- Use them for independent read-only audits, parallel documentation checks, or
  clearly separable implementation tasks.
- Avoid them for small single-file edits, sensitive cleanup, destructive
  operations, or changes that need one continuous judgment thread.
- The main agent remains responsible for integrating and verifying any result.

## Project Goal

Tutor Recommendation turns a local student profile plus a target faculty
directory into auditable teacher recommendation workbooks:

- collect faculty directory and homepage fields,
- match against configurable profile keywords,
- add DBLP, arXiv, known webpage, and optional bounded web-search evidence,
- classify candidates into `强烈建议`, `可以考虑`, and `暂不优先`,
- keep recommendation reasons and evidence sources reviewable,
- track manual contact status locally through the viewer.

## Key Files

- `README.md`: public project overview and quick start.
- `requirements.txt`: core runtime dependencies.
- `data/templates/student_profile.example.json`: public placeholder profile.
- `data/templates/dblp_overrides.example.json`: public DBLP override format.
- `data/templates/web_search_curated.example.json`: public curated search format.
- `src/tutor_recommendation/student_profile.py`: loads local profile data from
  `data/private/student_profile.json` or `STUDENT_PROFILE_PATH`.
- `src/tutor_recommendation/ranking_policy.py`: unified scoring, anchor, and
  recommendation policy used by every research stage.
- `src/tutor_recommendation/teacher_identity.py`: stable teacher IDs and
  identity confidence.
- `src/tutor_recommendation/run_manifest.py`: run provenance and checkpoint
  fingerprint inputs.
- `src/tutor_recommendation/teacher_match_targets.py`: target registry.
- `src/tutor_recommendation/first_pass_research.py`: directory/homepage
  collection, target-specific PDF supplements, and first-pass scoring.
- `src/tutor_recommendation/dblp_research.py`: DBLP author disambiguation and
  recent-paper evidence.
- `src/tutor_recommendation/teacher_research_completion.py`: arXiv and known
  webpage evidence completion.
- `src/tutor_recommendation/supplement_web_search_research.py`: optional
  bounded web-search supplement.
- `src/tutor_recommendation/contact_status.py`: local contact-state schema.
- `src/tutor_recommendation/viewer_server.py` and `viewer/`: local dashboard.
- Root `*.py` files are thin CLI wrappers that add `src` to `sys.path`.

## Common Commands

From the repository root:

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m pip install -r requirements.txt
```

Prepare a local profile:

```powershell
Copy-Item data/templates/student_profile.example.json data/private/student_profile.json
```

Run the three-stage workflow for a target key:

```powershell
python build_teacher_match.py <target>
python update_teacher_match_with_dblp.py <target>
python complete_teacher_research.py <target>
```

List supported targets:

```powershell
python build_teacher_match.py --help
```

Run only final workbook reconstruction from checkpoint:

```powershell
python complete_teacher_research.py <target> --finalize-only
```

Audit checkpoint coverage and shadow-score current outputs:

```powershell
python checkpoint_doctor.py <target>
python result_quality_audit.py --fail-on-violations
```

Run the unit tests:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
python -m unittest discover -s tests -v
```

Launch the local dashboard:

```powershell
.\start_viewer.bat
```

or:

```bash
./start_viewer.sh
```

Manual server entry:

```powershell
python viewer_server.py --port 8765
```

If the frontend reports `/api/session` as 404, an old viewer process is still
using the port. Stop it and rerun the launcher; do not delete contact state.

Sync local contact state back to workbooks:

```powershell
python sync_contact_status_to_workbooks.py
```

## Output Contract

Generated outputs are local-only and ignored:

```text
outputs/<school_slug>/<college_slug>/
```

Typical files:

- `<school_slug>_<college_slug>_teacher_match.xlsx`
- `<school_slug>_<college_slug>_teacher_match_dblp.xlsx`
- `<school_slug>_<college_slug>_teacher_match_full_research.xlsx`
- `full_research_checkpoint.jsonl`
- `dblp_cache/`
- `arxiv_cache/`
- `web_cache/`
- optional `pdf_cache/`
- optional `web_search_cache/`

The dashboard stores manual contact state in `outputs/contact_status.json`.
Excel workbooks are view/delivery artifacts; JSON is the local editable source
for contact state.
Contact columns are `套磁情况`, `套磁时间`, `回复情况`, and `回复情况备注`.
Valid contact statuses are `已套磁`, `先不考虑`, `不可能`, and `不匹配`.

## Evidence Rules

- Student matching must come from the loaded local profile, not hard-coded
  author-specific directions.
- Formal runs fail closed when the private profile is missing or invalid. The
  public template requires an explicit `--demo-profile` flag.
- Homepage and official directory text are baseline evidence.
- Official PDF advisor libraries or team introductions may supplement
  direction, team, and source columns when a target exposes such attachments.
- Overlapping targets from the same university should be built in one
  `build_teacher_match.py` command so cross-target de-duplication can run.
- De-duplication only auto-merges strong person identity URLs. Same-school,
  same-name rows without positive identity evidence stay separate and are
  marked for review. Do not merge by name inside a single target.
- Generic directory pages, login pages, lab homepages, and anchor-only list
  pages must not be treated as person identity URLs.
- Generic AI, LLM, NLP, multimodal, and agent terms should not drive matching
  unless the loaded profile assigns them meaningful weight.
- DBLP high-confidence matches can strengthen ranking only when homepage,
  official directory, or PDF evidence provides an explicit core direction
  anchor. DBLP-only keyword hits stay auxiliary.
- DBLP low-confidence or ambiguous matches require manual review.
- arXiv is auxiliary because author-name ambiguity is high.
- Low-confidence arXiv evidence must not alone produce `强烈建议`.
- Webpage evidence only confirms known URLs unless the optional web-search
  supplement is run.
- Automatic bounded web search is discovery-only. Manually confirmed sources
  may provide limited support only when an official core-direction anchor
  already exists.
- Every recommendation needs a readable reason and source columns.
- The viewer must display ranking-policy outputs rather than re-score rows in
  JavaScript. Keep official direction, matched profile terms, and auxiliary
  DBLP/arXiv/web signals visually separate; missing structured fields in old
  workbooks should be labeled as old data instead of inferred.
- Finalize-only reconstruction requires complete valid checkpoint coverage by
  default. Use `checkpoint_doctor.py` before relying on it; partial output must
  be explicitly requested.

## Adding A Target

1. Choose `school_slug`, `college_slug`, and a target key.
2. Register the target in `src/tutor_recommendation/teacher_match_targets.py`.
3. Add or extend the directory parser in
   `src/tutor_recommendation/first_pass_research.py`.
4. Keep output columns stable for DBLP, arXiv, webpage, and viewer stages.
5. Run the three-stage workflow and manually inspect high-value ambiguous rows.
6. Store manual DBLP overrides in ignored `data/private/dblp_overrides.json`.
7. Store manually reviewed web-search evidence in ignored
   `data/private/web_search_curated.json`.

## Documentation Rules

When workflow behavior changes, update public docs at the appropriate level:

- `README.md`: user-facing overview and quick start.
- `docs/teacher-matching-workflow.md`: reusable methodology.
- `docs/runbook.md`: commands, checks, and troubleshooting.
- `docs/output-organization.md`: output layout and cache rules.
- `docs/handoff.md`: public handoff template only.

Local progress, applicant-specific choices, target result counts, and crawl
audits belong in ignored `docs/private/`, not in tracked files.
