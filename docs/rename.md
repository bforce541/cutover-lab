# Rename the project

## Change the display name

1. Edit the `name`, `subtitle` and optional short `mark` in `brand.json`.
2. Restart FastAPI and reload the app. The masthead and browser title read the configuration from the API. Regenerate evidence if you want its Markdown heading to reflect the new name.
3. Update documentation headings as desired. The Python import `migration_rehearsal`, API paths and cloud resource names can stay the same.

## Change the repository and checkout names

1. In the private repository’s GitHub **Settings → General**, change the repository name. Confirm it still shows **Private**.
2. Stop running processes, leave the checkout directory, and rename it to the new name. Open the renamed checkout and update the remote with `git remote set-url origin <new-private-repository-url>`. Verify it with `git remote -v` and `gh repo view --json nameWithOwner,visibility,url`.
3. Refresh the project-local environment if it moved. Virtual environments can contain path-specific launchers. Use `uv sync --locked` and rebuild the frontend with `npm ci && npm run build`.
4. Launch with the same commands in the renamed checkout. The downloader, fixture, brand file and built app resolve relative to the checkout. If you start from a fresh clone, rerun the download and copy your local configuration as needed.

The rename acceptance run uses an alternate checkout name and a temporary display name. See the [verification index](../evidence/README.md) for the observed result.
