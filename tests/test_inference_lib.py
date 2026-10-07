"""
测试推理的阈值应用和兜底逻辑
evaluate与serve共用，确保行为一致
"""
import numpy as np

from scripts.finetune.inference_lib import apply_threshold


def test_over_threshold_multi_hit():
    """测试多命中：超过阈值的标签都被激活"""
    probs = np.array([[0.9, 0.85, 0.1]])
    assert apply_threshold(probs, 0.45).tolist() == [[1, 1, 0]]


def test_all_below_falls_back_to_argmax():
    """测试兜底逻辑：全不过线时取最高分"""
    probs = np.array([[0.2, 0.05, 0.31]])
    assert apply_threshold(probs, 0.45).tolist() == [[0, 0, 1]]


def test_boundary_value_hits():
    """测试边界值：等于阈值时命中"""
    probs = np.array([[0.45, 0.449, 0.0]])
    assert apply_threshold(probs, 0.45).tolist() == [[1, 0, 0]]


def test_batch_rows_independent():
    """测试批量独立：每行独立应用阈值"""
    probs = np.array([[0.9, 0.1], [0.1, 0.2]])
    out = apply_threshold(probs, 0.45)
    assert out.tolist() == [[1, 0], [0, 1]]
