import os

from chanlun_quant.config import Config


def test_from_env_overrides_and_types():
    keys = [
        "CLQ_MIN_BARS_PER_PEN",
        "CLQ_CENTRAL_OVERLAP_RATIO",
        "CLQ_STRICT_FEATURE_SEQUENCE",
        "CLQ_LEVELS",
        "CLQ_MACD_AREA_MODE",
        "CLQ_USE_LLM",
        "CLQ_IB_PORT",
        "CLQ_MAX_POSITION",
    ]
    backup = {key: os.environ.get(key) for key in keys}
    try:
        os.environ["CLQ_MIN_BARS_PER_PEN"] = "7"
        os.environ["CLQ_CENTRAL_OVERLAP_RATIO"] = "0.3"
        os.environ["CLQ_STRICT_FEATURE_SEQUENCE"] = "false"
        os.environ["CLQ_LEVELS"] = "15m,2h,1d"
        os.environ["CLQ_MACD_AREA_MODE"] = "dif"
        os.environ["CLQ_USE_LLM"] = "0"
        os.environ["CLQ_IB_PORT"] = "4001"
        os.environ["CLQ_MAX_POSITION"] = "5000"

        cfg = Config.from_env()
        assert cfg.min_bars_per_pen == 7
        assert abs(cfg.central_overlap_ratio - 0.3) < 1e-12
        assert cfg.strict_feature_sequence is False
        assert cfg.levels == ("15m", "2h", "1d")
        assert cfg.macd_area_mode == "dif"
        assert cfg.use_llm is False
        assert cfg.ib_port == 4001
        assert cfg.max_position == 5000
    finally:
        for key, value in backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
