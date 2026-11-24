# Releasing an update

Installed copies check `https://github.com/<owner>/<repo>/releases/latest/download/latest.json` each time
they start, so publishing a GitHub release is all it takes to update everyone.

1. Make the change in `app/` and test it.
2. Raise the number in `app/VERSION` by one. (Versions only go up. A version that failed to start on someone's
   computer is never retried there, so a fix must be a new number.)
3. If `requirements.txt` changed, installed copies install the new packages on their next start; nothing else to do.
4. Build: `python tools/build.py --repo <owner>/<repo>`
5. Publish a GitHub release tagged `v<VERSION>` with all four files from `dist/` attached:
   `scene-filter-app-<VERSION>.zip`, `latest.json`, `Scene_Filter_for_Mac.zip`, `Scene_Filter_for_Windows.zip`.
   It must be marked as the **latest** release (not a pre-release or draft), or installed copies won't see it.

Changes to `launcher/`, `mac/` or `windows/` reach only new downloads, not installed copies. Keep them rare and
backwards compatible; put everything possible in `app/`.
