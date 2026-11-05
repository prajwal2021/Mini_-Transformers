# Analysis-stream failures (F-A###)

- F-A001 A shell command with a bare `cat > $TMP/x.py` waited on stdin and hung for 2 minutes; no data was affected. Use the scratchpad directory and explicit heredocs.
