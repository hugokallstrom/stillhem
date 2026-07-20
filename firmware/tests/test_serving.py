from stillhem.serving import SERVING_QPM_THRESHOLD, is_serving, queries_per_minute


def test_qpm_basic_rate():
    # 300 queries over 60 seconds = 300/min
    assert queries_per_minute(1000.0, 0, 1060.0, 300) == 300.0


def test_qpm_zero_when_no_time_elapsed():
    assert queries_per_minute(1000.0, 0, 1000.0, 50) == 0.0


def test_qpm_zero_on_counter_reset():
    # cur_count < prev_count means Unbound restarted; treat as no signal
    assert queries_per_minute(1000.0, 500, 1060.0, 10) == 0.0


def test_is_serving_threshold():
    assert is_serving(SERVING_QPM_THRESHOLD) is True
    assert is_serving(SERVING_QPM_THRESHOLD - 0.1) is False
    assert is_serving(0.0) is False
