# Legacy Private Input Data

New Agent-first work should use `user_private/`. This directory remains readable
for compatibility with existing local profiles and overrides.

The matching code first reads `user_private/profile/student_profile.json`, then
falls back to `data/private/student_profile.json`. You can also point to another
profile with:

```powershell
$env:STUDENT_PROFILE_PATH='D:\path\to\student_profile.json'
```

Formal commands fail when the private profile is missing or invalid. The public
example profile is only available through an explicit `--demo-profile` flag and
must not be used for real application decisions.

Files in this directory are intentionally ignored except for this README.

Common local-only files:

- `student_profile.json`
- `dblp_overrides.json`
- `web_search_curated.json`
- `seu_college_affiliations.json`
