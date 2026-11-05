# Failures (eval stream)

- E-F001 **Plan A:** swap the entity in a canonical prefix with `str.replace`. **Failed:** "cat" occurs inside "certificate". **Fix:** word-boundary regex, exactly one match required.
- E-F002 **Plan A:** key mock ground truth by (fact, variant). **Failed:** the canonical prompt is identical in val and test, so one text had two scores. **Fix:** key by prompt text.
- E-F003 **Tooling:** the Git Bash tool failed (`add_item` fatal error); all commands were run through PowerShell. The editable install of `slm` points at the main checkout, so tests here need `PYTHONPATH=src`.