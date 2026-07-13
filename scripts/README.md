# Scripts

Normal Agent-driven work uses the repository-root `tutor.py` bootstrap or the installed `tutor` command.

- `start_viewer.bat` / `start_viewer.sh`: optional direct Viewer launchers.
- `legacy/`: compatibility wrappers around package implementations. They preserve advanced and historical command options while the unified Agent CLI matures.

New business logic belongs in `src/tutor_recommendation/`, not in these wrappers.
