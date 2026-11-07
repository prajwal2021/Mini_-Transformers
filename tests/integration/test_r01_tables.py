# ruff: noqa: E501
"""R01: error_class and the ranking ranks travel into qa.csv; the summary tables are written."""

import pandas as pd

from slm.integration import tables as T

from .test_tables import KB_SPLIT, probe_rows, qa_predictions


def with_extras() -> pd.DataFrame:
    q = qa_predictions()
    q["error_class"] = ["correct" if v else "format_failure" for v in q["exact_value_match"]]
    for c in ("rank_value", "rank_value_norm", "rank_sentence", "rank_sentence_norm"):
        q[c] = 1
    return q


def probes() -> pd.DataFrame:
    return pd.concat([probe_rows({"F001": [1, 1, 0], "F002": [0, 0, 0]}, seed=s) for s in (0, 1)])


def test_qa_table_carries_the_extra_columns_when_present_and_not_otherwise():
    with_cols = T.qa_table(with_extras(), probes(), KB_SPLIT)
    assert {"error_class", "rank_value", "rank_sentence_norm"} <= set(with_cols.columns)
    plain = T.qa_table(qa_predictions(), probes(), KB_SPLIT)
    assert "error_class" not in plain.columns


def test_build_tables_writes_the_taxonomy_and_ranking_summaries(tmp_path):
    paths = T.write_qa_summaries(with_extras(), tmp_path)
    tax = pd.read_csv(paths["error_taxonomy"])
    assert set(tax.columns) >= {"checkpoint", "prompt_mode", "eval_set", "error_class", "n", "share"}
    assert set(tax["error_class"]) == {"correct", "right_type_wrong_value", "out_of_kb_hallucination", "wrong_attribute", "format_failure"}
    assert tax.groupby(["checkpoint", "prompt_mode", "eval_set"])["n"].sum().min() > 0
    rank = pd.read_csv(paths["ranking"])
    assert (rank["rank_value_acc"] == 1.0).all()
