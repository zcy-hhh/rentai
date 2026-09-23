# 作者：zcy
"""M4 评测测试：指标可计算且在合法区间。"""
from __future__ import annotations

from evals.run import run_eval


def test_eval_metrics_in_valid_range() -> None:
    metrics = run_eval()
    assert metrics["match_cases"] > 0
    assert 0 <= metrics["match_precision@k"] <= 1
    assert 0 <= metrics["match_recall"] <= 1
    assert 0 <= metrics["risk_recall"] <= 1


def test_eval_sanity_perfect_on_self_consistent_data() -> None:
    """当前评测集与实现同源（确定性+同 mock），应自洽为 1.0，作为机制正确性校验。"""
    metrics = run_eval()
    assert metrics["match_precision@k"] == 1.0
    assert metrics["match_recall"] == 1.0
