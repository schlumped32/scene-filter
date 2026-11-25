# Releasing an update

Installed copies check `https://github.com/<owner>/<repo>/releases/latest/download/latest.json` each time
they start, so publishing a GitHub release is all it takes to update everyone.

1. Make the change in `app/` and test it.
2. Raise the number in `app/VERSION` by one. (Versions only go up. A version that failed to start on someone's
   computer is never retried there, so a fix must be a new number.)
3. If `requirements.txt` changed, installed copies install the new packages on their next start; nothing else to do.
4. Write the release notes in `release-notes/v<VERSION>.md` (what's better, what's fixed).
5. Commit, then push a tag: `git tag v<VERSION> && git push origin main v<VERSION>`.
   The **Release** workflow (`.github/workflows/release.yml`) checks the tag matches `app/VERSION`, runs
   `tools/build.py`, and publishes the GitHub release as the latest one with all four files attached:
   `scene-filter-app-<VERSION>.zip`, `latest.json`, `Scene_Filter_for_Mac.zip`, `Scene_Filter_for_Windows.zip`.
   Installed copies pick it up the next time they start.

To build by hand instead (for testing): `python tools/build.py --repo <owner>/<repo>` writes them to `dist/`.

Changes to `launcher/`, `mac/` or `windows/` reach only new downloads, not installed copies. Keep them rare and
backwards compatible; put everything possible in `app/`.
