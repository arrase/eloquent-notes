# Release Process

Eloquent Notes uses semantic versioning. The version lives in exactly one
place: the `version` field of `pyproject.toml`. Git tags and GitHub releases
are derived from it and must never be created independently.

## Procedure

1. Create a branch and bump the version:

   ```bash
   git checkout -b chore/bump-v0.4.0
   # edit version = "0.4.0" in pyproject.toml
   ```

2. Verify the whole suite passes, then open a PR:

   ```bash
   pytest -q
   ruff check .
   mypy eloquent_notes
   ```

3. Merge the PR to `main`.

4. Tag the merge commit and publish the release:

   ```bash
   git checkout main && git pull --ff-only
   git tag -a v0.4.0 -m "v0.4.0"
   git push origin v0.4.0
   gh release create v0.4.0 --verify-tag --title "v0.4.0" --notes-file notes.md
   ```

5. Delete the release branch:

   ```bash
   git push origin --delete chore/bump-v0.4.0
   ```

## Enforcement

`tests/test_version.py` fails the build if the version ever drifts. It checks
that:

- the `pyproject.toml` version is valid `MAJOR.MINOR.PATCH`
- the package exposes a real installed version, not the uninstalled fallback
- `pyproject.toml` and the installed distribution metadata agree
- the newest `v*` tag equals `v<pyproject version>`

That last check is why the bump must be merged **before** the tag is pushed:
tagging first is exactly how v0.2.9 shipped with `pyproject.toml` still
declaring `0.2.8`.

The tag check skips when the checkout has no version tags, so shallow clones
and source tarballs are not broken by it.
