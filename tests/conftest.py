def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "slow: test that takes more than 30 seconds")
