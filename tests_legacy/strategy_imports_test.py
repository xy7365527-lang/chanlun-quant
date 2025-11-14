import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from chanlun.strategy.strategy_a_d_mmd_test import StrategyADMMDTest
from chanlun.strategy.strategy_test import StrategyTest


def test_strategy_ad_mmd_can_instantiate() -> None:
    strategy = StrategyADMMDTest()
    assert strategy.mode == "test"
    assert strategy.filter_key == "loss_rate"
    assert strategy.filter_reverse is True
    assert strategy.clear() is None


def test_strategy_test_can_instantiate() -> None:
    strategy = StrategyTest()
    assert strategy.clear() is None
