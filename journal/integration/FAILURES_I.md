# Integration failures (I-F###)

| id | Plan A | What failed (evidence) | Root cause | Plan B | Lesson |
|---|---|---|---|---|---|
| I-F001 | `pip install -e .` with the default `python` to point `slm` at this worktree | The default interpreter is the system Python 3.12, which has no torch; pip began downloading the 2.5 GB CUDA wheel and ran past the 120 s tool timeout in the background; `import slm` failed | Dependencies live only in the main checkout's `.venv`; editing that venv would have repointed Window 1's editable install | Stopped the stray install, built a separate `.venv` here that borrows main's `site-packages` through a `.pth` and installs only this package (`--no-deps`) (I-D001) | Check which interpreter owns the dependencies before an editable install in a worktree |
