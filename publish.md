# How to publish this library

This repository currently uses a manual PyPI release flow. Do not publish from
GitHub Actions unless the project explicitly decides to add an automated release
workflow later.

## Manual release

1. Bump `sqlalchemy_risingwave/__init__.py` and update `CHANGELOG.md`.
2. Merge the release PR.
3. Check out the release commit on `main`.
4. Install the build tools:

   ```sh
   python3 -m pip install --upgrade build twine
   ```

5. Build clean distributions:

   ```sh
   rm -rf dist/ build/ *.egg-info
   python3 -m build
   ```

6. Validate the distributions:

   ```sh
   python3 -m twine check dist/*
   ```

7. Upload the distributions to PyPI:

   ```sh
   twine upload dist/*
   ```

8. After PyPI upload succeeds, create and push the matching git tag:

   ```sh
   VERSION=2.1.0
   git tag "v$VERSION"
   git push origin "v$VERSION"
   ```
