# Next steps — manual one-time setup

This project uses the following external services. Each section below contains the
one-time human steps you need to complete before CI / publish flows will work.

- [pypi](#pypi)

## pypi

## PyPI publish — trusted publishing setup

1. Sign in at https://pypi.org/account/login/
2. Generate a project-scoped API token at https://pypi.org/manage/account/token/
3. (First time only) Reserve the package name with twine:
   ```bash
   uv tool install twine
   twine upload --username __token__ --password <pypi-token> dist/*
   ```
4. After project exists on PyPI, configure trusted publishing at:
   https://pypi.org/manage/project/<NAME>/settings/publishing/
   - Owner: <github-org>
   - Repository: <github-repo>
   - Workflow name: ci.yml
5. Future tag pushes will publish automatically — no token needed.
