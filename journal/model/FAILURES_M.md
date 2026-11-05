# Model-stream failures (M-F###)

## M-F001 torch.compile unavailable on this machine
- Plan A: compare eager and `torch.compile` throughput in the GPU smoke test.
- What failed: `torch._inductor.exc.TritonMissing: Cannot find a working triton installation` (torch 2.11.0+cu128, native Windows). Evidence: `reports/model/gpu_smoke.json`, key `compiled.error`.
- Root cause: Triton is not installed or supported on native Windows (already noted in DESIGN, D-011).
- Plan B: train eager. At 180k positions/s the full 20-epoch run takes about 2 minutes, so compile is not needed.
- Lesson: do not spend time on compile for this project.

## M-F002 Init-loss test failed on the first run
- Test `test_init_loss_is_ln_vocab` used `labels = input_ids`; with tied embeddings each token's own embedding raises its own logit, so the loss started at 5.5 instead of ln V = 6.24.
- Root cause: a flaw in the test, not in the model. The fix is independent random targets (loss 6.2). Worth remembering for P05: the init loss is only about ln V when targets are unrelated to inputs, and real next-token targets are.

## M-F003 First resume/run-directory test asserted on the wrong thing
- `test_run_directory_contents` first assumed 6 steps per epoch (it is 3) and then asserted val loss falls on random token data; with 24 random tiny documents the val loss legitimately rises once the model overfits. Fixed by computing steps from the dataset and asserting on train loss. Lesson: loss-direction assertions belong on the training loss or on data with structure.

## M-F004 Shell instability
- The Git Bash tool failed intermittently (`add_item ... errno 1`) and mangled heredocs containing quotes or backslash escapes; two edits silently did not apply and were redone with the file tools. PowerShell was used for test runs. No project impact.
