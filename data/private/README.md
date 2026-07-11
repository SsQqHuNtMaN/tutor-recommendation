# Private Input Data

Put your own resume, application materials, and optional local profile here.

The matching code reads `data/private/student_profile.json` by default. You can
also point to another profile with:

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
