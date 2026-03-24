from ezrules.backend.api_v2.routes import backtesting as backtesting_routes


def test_store_eager_backtest_result_keeps_cache_bounded():
    original_cache = backtesting_routes._EAGER_BACKTEST_RESULTS.copy()

    try:
        backtesting_routes._EAGER_BACKTEST_RESULTS.clear()

        for index in range(backtesting_routes._MAX_EAGER_BACKTEST_RESULTS + 3):
            backtesting_routes._store_eager_backtest_result(
                f"task-{index}",
                {"stored_result": {"index": index}},
            )

        assert len(backtesting_routes._EAGER_BACKTEST_RESULTS) == backtesting_routes._MAX_EAGER_BACKTEST_RESULTS
        assert "task-0" not in backtesting_routes._EAGER_BACKTEST_RESULTS
        assert "task-1" not in backtesting_routes._EAGER_BACKTEST_RESULTS
        assert "task-2" not in backtesting_routes._EAGER_BACKTEST_RESULTS
        assert (
            f"task-{backtesting_routes._MAX_EAGER_BACKTEST_RESULTS + 2}" in backtesting_routes._EAGER_BACKTEST_RESULTS
        )
    finally:
        backtesting_routes._EAGER_BACKTEST_RESULTS.clear()
        backtesting_routes._EAGER_BACKTEST_RESULTS.update(original_cache)
