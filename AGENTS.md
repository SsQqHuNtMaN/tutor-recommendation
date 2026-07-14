# Codex Project Guide: Tutor Recommendation

This file is safe to keep in the public repository. It should describe stable
engineering rules, commands, and privacy boundaries only.

## Privacy Boundary

- Do not store personal resumes, application forms, student profiles, contact
  status, generated Excel files, caches, or current crawl results in tracked
  files.
- User-provided materials and the confirmed profile live under `user_private/`;
  only its README and example request are tracked. `data/private/` remains a
  legacy-compatible private path. Local agent context lives in `docs/private/`.
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
- add target-specific publication, arXiv, known webpage, and optional bounded
  web-search evidence,
- classify candidates into `强烈建议`, `可以考虑`, and `暂不优先`,
- keep recommendation reasons and evidence sources reviewable,
- track manual contact status locally through the viewer.

## Agent-First Workflow

- The user supplies private materials, target school/college, preferences, and
  confirmation of uncertain profile fields. The Coding Agent performs the
  commands, target integration, evidence workflow, checks, and Viewer launch.
- Start by reading `user_private/request.md` when it exists and inspecting the
  selected profile's source directory (or legacy `user_private/source/`). Never
  commit either path's private contents.
- Generate only a draft profile from source materials. A user-confirmed
  named profile under `user_private/profiles/<profile_id>/student_profile.json`
  or the legacy `user_private/profile/student_profile.json` is required for
  formal runs.
- Check every requested target with `tutor targets --check <target>`. If it is
  missing, follow `docs/agent-workflow.md`: find an official directory, add the
  target and collector binding, add tests, then run the workflow. Do not ask the
  user to implement project code.

## Key Files

- `README.md`: public project overview and quick start.
- `docs/agent-workflow.md`: authoritative Agent intake, missing-target, run,
  and validation workflow.
- `user_private/README.md`: safe public instructions for the ignored private
  materials workspace.
- `src/tutor_recommendation/cli.py`: unified deterministic tools used by the
  Coding Agent; root scripts remain compatibility wrappers.
- `src/tutor_recommendation/collectors/registry.py`: explicit target-to-collector
  binding; every registered target must have an implementation.
- `requirements.txt`: core runtime dependencies.
- `data/templates/`: public placeholder profile and reviewed-override schemas.
- `src/tutor_recommendation/student_profile.py`: loads the confirmed profile
  selected by the profile registry, the legacy private path, or
  `STUDENT_PROFILE_PATH`.
- `src/tutor_recommendation/profile_registry.py`: named profile discovery,
  active selection, and profile-specific output roots.
- `src/tutor_recommendation/ranking_policy.py`: unified scoring, anchor, and
  recommendation policy used by every research stage.
- `src/tutor_recommendation/teacher_identity.py`: stable teacher IDs and
  identity confidence.
- `src/tutor_recommendation/run_manifest.py`: run provenance and checkpoint
  fingerprint inputs.
- `src/tutor_recommendation/teacher_match_targets.py`: target registry.
- `src/tutor_recommendation/first_pass_research.py`: compatibility first-pass
  orchestration, target-specific PDF supplements, and first-pass scoring.
- `src/tutor_recommendation/dblp_research.py`: DBLP author disambiguation and
  recent-paper evidence.
- `src/tutor_recommendation/publication_adapters.py` and
  `math_publication_research.py`: source-neutral mathematics publication
  evidence using official lists, zbMATH Open, and optional OpenAlex.
- `src/tutor_recommendation/teacher_research_completion.py`: arXiv and known
  webpage evidence completion.
- `src/tutor_recommendation/supplement_web_search_research.py`: optional
  bounded web-search supplement.
- `src/tutor_recommendation/contact_status.py`: local contact-state schema.
- `src/tutor_recommendation/viewer_server.py` and `viewer/`: local dashboard,
  four-week contact strip, teacher list, and detail workspace.
- `docs/viewer-integrated-layout.md`: implemented calendar-above-list layout,
  shared selection behavior, and collapsible detail sidebar contract.
- `tutor.py`: repository-root launcher; legacy wrappers live in `scripts/legacy/`.

## Common Commands

From the repository root, install the package in editable mode:

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m pip install -e .
```

Prepare the private workspace and extract a draft for user confirmation:

```powershell
tutor setup
tutor profile extract
tutor profile validate
tutor profile list
tutor profile use <profile_id>
```

Check target support and run the workflow:

```powershell
tutor targets --check <target>
tutor run <target>
```

List supported targets:

```powershell
tutor targets
```

Run only final workbook reconstruction from checkpoint:

```powershell
python scripts/legacy/complete_teacher_research.py <target> --finalize-only
```

Audit checkpoint coverage and shadow-score current outputs:

```powershell
tutor doctor <target>
tutor audit --fail-on-violations
```

Run the unit tests:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
python -m unittest discover -s tests -v
```

Launch the local dashboard:

```powershell
tutor view
```

Windows users may instead double-click the repository-root `start_viewer.bat`.
It reuses a compatible running Viewer and selects another loopback port when
the preferred port is occupied by an older service.

or:

```bash
./scripts/start_viewer.sh
```

Manual server entry:

```powershell
python tutor.py view --port 8765
```

If the frontend reports `/api/session` as 404, an old viewer process is still
using the port. Stop it and rerun the launcher; do not delete contact state.

Sync local contact state back to workbooks:

```powershell
python scripts/legacy/sync_contact_status_to_workbooks.py
```

## Output Contract

Generated outputs are local-only and ignored. Legacy/default runs use the first
root; named profiles use the second:

```text
outputs/<school_slug>/<college_slug>/
outputs/by_profile/<profile_id>/<school_slug>/<college_slug>/
```

Typical files:

- `<school_slug>_<college_slug>_teacher_match.xlsx`
- `<school_slug>_<college_slug>_teacher_match_dblp.xlsx`
- `<school_slug>_<college_slug>_teacher_match_publications.xlsx` for mathematics
  evidence profiles
- `<school_slug>_<college_slug>_teacher_match_full_research.xlsx`
- `full_research_checkpoint.jsonl`
- `dblp_cache/`
- `arxiv_cache/`
- `web_cache/`
- optional `pdf_cache/`
- optional `web_search_cache/`
- optional `math_publication_cache/`

The dashboard stores manual contact state beside the selected profile root:
`outputs/contact_status.json` for legacy/default runs or
`outputs/by_profile/<profile_id>/contact_status.json` for named profiles. Excel
workbooks are view/delivery artifacts; JSON is the local editable source.
Contact columns are `套磁情况`, `套磁时间`, `回复情况`, `约面试时间`, and
`回复情况备注`.
Valid contact statuses are `已套磁`, `先不考虑`, `不可能`, and `不匹配`.

## Evidence Rules

- Student matching must come from the loaded local profile, not hard-coded
  author-specific directions.
- Formal runs fail closed when the private profile is missing or invalid. The
  public template requires an explicit `--demo-profile` flag.
- Homepage and official directory text are baseline evidence.
- Official PDF advisor libraries or team introductions may supplement
  direction, team, and source columns when a target exposes such attachments.
- Overlapping targets from the same university should be passed to one
  `tutor run` command so first-pass cross-target de-duplication can run.
- Targets in the same explicit `cross_target_overlap_group` may preserve the
  same stable teacher ID across multiple colleges when official affiliation
  evidence supports a real multi-college relationship. SEU CSE, Software, and
  AI use this model.
- De-duplication only auto-merges strong person identity URLs. Same-school,
  same-name rows without positive identity evidence stay separate and are
  marked for review. Do not merge by name inside a single target.
- Generic directory pages, login pages, lab homepages, and anchor-only list
  pages must not be treated as person identity URLs.
- College affiliation must come from official rosters, admissions material,
  teacher pages, or a local reviewed override. Never infer affiliation from a
  research direction; unresolved records stay marked for review.
- Generic AI, LLM, NLP, multimodal, and agent terms should not drive matching
  unless the loaded profile assigns them meaningful weight.
- DBLP high-confidence matches can strengthen ranking only when homepage,
  official directory, or PDF evidence provides an explicit core direction
  anchor. DBLP-only keyword hits stay auxiliary.
- DBLP low-confidence or ambiguous matches require manual review.
- Mathematics targets use official publication lists and zbMATH Open as the
  primary publication path, with optional OpenAlex when `OPENALEX_API_KEY` is
  configured. Name-only candidates never affect ranking.
- Source-neutral publication evidence can strengthen a recommendation only
  after medium/high author disambiguation and an official core-direction
  anchor. Missing database records are neutral.
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
  default. Use `tutor doctor` before relying on it; partial output must
  be explicitly requested.

## Adding A Target

1. Choose `school_slug`, `college_slug`, and a target key.
2. Register the target in `src/tutor_recommendation/teacher_match_targets.py`.
3. Add or extend an official directory parser under
   `src/tutor_recommendation/collectors/`; do not expand the compatibility
   first-pass monolith for a new target.
4. Bind the target in `src/tutor_recommendation/collectors/registry.py`.
5. Add deterministic parser/registry regression coverage.
6. Keep output columns stable for DBLP, arXiv, webpage, and viewer stages.
7. Run the three-stage workflow and manually inspect high-value ambiguous rows.
8. Prefer ignored `user_private/overrides/` for reviewed overrides; legacy
   `data/private/` files remain readable during migration.

## Documentation Rules

When workflow behavior changes, update public docs at the appropriate level:

- `README.md`: user-facing overview and quick start.
- `docs/teacher-matching-workflow.md`: reusable methodology.
- `docs/runbook.md`: commands, checks, and troubleshooting.
- `docs/output-organization.md`: output layout and cache rules.
- `docs/handoff.md`: public handoff template only.

Local progress, applicant-specific choices, target result counts, and crawl
audits belong in ignored `docs/private/`, not in tracked files.
Future exploration, implementation plans, TODO checklists, local validation
queues, and temporary handoff notes also belong in `docs/private/`; public docs
describe only implemented behavior, reusable methodology, and stable contracts.
