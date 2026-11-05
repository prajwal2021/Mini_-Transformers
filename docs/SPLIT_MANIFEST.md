# Split manifest (provisional format, v1)

The data stream should emit one manifest file, for example `data/splits.json`. Every reader on the
model side (tokenizer training, token cache, training loop) accepts only files this manifest lists,
in the split the caller is allowed to use, with the recorded hash.

```json
{
  "version": 1,
  "files": {
    "corpus/train_000.jsonl": {"split": "train", "sha256": "<64 hex chars>"},
    "corpus/val_000.jsonl":   {"split": "val",   "sha256": "<64 hex chars>"},
    "corpus/test_000.jsonl":  {"split": "test",  "sha256": "<64 hex chars>"}
  }
}
```

Rules:
- `version` is 1. Anything else is refused.
- Keys are file paths **relative to the manifest's own directory**, with `/` separators.
- `split` is one of `train`, `val`, `test`. Anything else is refused.
- `sha256` is the SHA-256 of the file's raw bytes. Writing or checking it on a text file that git
  may convert (CRLF) changes the hash, so mark corpus files binary in `.gitattributes`
  (`data/**  -text`) or compute the hash after checkout.
- File content: `.jsonl` with one `{"text": "<document>"}` per line, or `.txt` with documents
  separated by a form feed (`\f`). This is provisional (M-D009); only `slm.tokenizer.parse_documents`
  would change.
- One document is one training unit. Documents are tokenised whole, followed by `<|eos|>`.

What the model side enforces:

| Reader | Allowed splits |
|---|---|
| `slm.tokenizer.train_tokenizer(manifest)` | `train` only |
| `slm.data_loading.tokenize_split` and the training loop | `train` and `val` |
| anything touching `test` | refused (`ValueError` / `ManifestError`) |

A file is refused when it is not listed, when it is listed under another split, or when its bytes no
longer match `sha256` (message names both hashes). File names are not inspected, so a validation
file called `part2.txt` is still refused for the tokenizer.

Python helper for writing one: `slm.split_manifest.build_manifest({path: split, ...}, out_path)`.
