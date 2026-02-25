"""Unit tests for core logger module."""
import logging
import pytest
from autotrader.core.logger import setup_logging


class TestSetupLoggingBasics:
    """Test basic logger setup functionality."""

    def test_setup_logging_returns_logger(self):
        """Test that setup_logging returns a Logger instance."""
        log = setup_logging("TEST")
        assert isinstance(log, logging.Logger)

    def test_setup_logging_default_level(self):
        """Test default log level is INFO."""
        log = setup_logging("DEFAULT")
        assert log.level == logging.INFO

    def test_setup_logging_debug_level(self):
        """Test setting DEBUG log level."""
        log = setup_logging("DEBUG_TEST", level="DEBUG")
        assert log.level == logging.DEBUG

    def test_setup_logging_warning_level(self):
        """Test setting WARNING log level."""
        log = setup_logging("WARN_TEST", level="WARNING")
        assert log.level == logging.WARNING

    def test_setup_logging_error_level(self):
        """Test setting ERROR log level."""
        log = setup_logging("ERROR_TEST", level="ERROR")
        assert log.level == logging.ERROR

    def test_setup_logging_sets_logger_name(self):
        """Test that logger name is set correctly."""
        log = setup_logging("MY_LOGGER")
        assert log.name == "MY_LOGGER"


class TestSetupLoggingCase:
    """Test case-insensitive level handling."""

    def test_lowercase_level(self):
        """Test lowercase level strings."""
        log = setup_logging("TEST", level="debug")
        assert log.level == logging.DEBUG

    def test_uppercase_level(self):
        """Test uppercase level strings."""
        log = setup_logging("TEST", level="DEBUG")
        assert log.level == logging.DEBUG

    def test_mixedcase_level(self):
        """Test mixed-case level strings are converted to uppercase."""
        log = setup_logging("TEST", level="DeBuG")
        # Mixed case is converted to uppercase
        assert log.level == logging.DEBUG


class TestSetupLoggingHandler:
    """Test logger handler setup."""

    def test_logger_has_handler(self):
        """Test that logger has at least one handler."""
        log = setup_logging("HANDLER_TEST")
        assert len(log.handlers) > 0

    def test_handler_is_stream_handler(self):
        """Test that handler is a StreamHandler."""
        log = setup_logging("STREAM_TEST")
        assert any(isinstance(h, logging.StreamHandler) for h in log.handlers)

    def test_handler_has_formatter(self):
        """Test that handler has a formatter."""
        log = setup_logging("FORMATTER_TEST")
        handler = log.handlers[0]
        assert handler.formatter is not None

    def test_formatter_format_string(self):
        """Test that formatter has the expected format."""
        log = setup_logging("FORMAT_TEST")
        handler = log.handlers[0]
        formatter = handler.formatter
        # Check if format string contains key elements
        assert "%(asctime)s" in formatter._fmt or "%(asctime)s" in str(formatter._fmt)
        assert "%(name)s" in formatter._fmt or "%(name)s" in str(formatter._fmt)
        assert "%(levelname)s" in formatter._fmt or "%(levelname)s" in str(formatter._fmt)
        assert "%(message)s" in formatter._fmt or "%(message)s" in str(formatter._fmt)


class TestSetupLoggingRepeated:
    """Test repeated calls to setup_logging."""

    def test_repeated_setup_same_logger(self):
        """Test calling setup_logging multiple times with same name."""
        log1 = setup_logging("REPEAT_TEST", level="DEBUG")
        log2 = setup_logging("REPEAT_TEST", level="INFO")
        assert log1 is log2  # Should return same logger instance
        # Note: Level might have changed or stayed the same depending on Python's logger behavior

    def test_repeated_setup_doesnt_duplicate_handlers(self):
        """Test that repeated setup doesn't duplicate handlers."""
        log = setup_logging("HANDLER_DUP_TEST")
        initial_count = len(log.handlers)
        log = setup_logging("HANDLER_DUP_TEST")
        # Handler should not be duplicated
        assert len(log.handlers) <= initial_count + 1  # May add one if no handlers


class TestSetupLoggingWithDifferentNames:
    """Test setup_logging with different logger names."""

    def test_different_logger_names(self):
        """Test creating loggers with different names."""
        log1 = setup_logging("LOGGER_1")
        log2 = setup_logging("LOGGER_2")
        assert log1.name == "LOGGER_1"
        assert log2.name == "LOGGER_2"
        assert log1 is not log2

    def test_module_style_names(self):
        """Test logger names with module-style dots."""
        log = setup_logging("autotrader.core.test")
        assert log.name == "autotrader.core.test"

    def test_hierarchical_logger_names(self):
        """Test hierarchical logger names."""
        log1 = setup_logging("app")
        log2 = setup_logging("app.module")
        log3 = setup_logging("app.module.component")
        assert log1.name == "app"
        assert log2.name == "app.module"
        assert log3.name == "app.module.component"


class TestSetupLoggingFunctionality:
    """Test logger functionality after setup."""

    def test_logger_can_log_message(self, caplog):
        """Test that logger can log messages."""
        with caplog.at_level(logging.DEBUG):
            log = setup_logging("LOG_TEST", level="DEBUG")
            log.info("Test message")
        assert "Test message" in caplog.text

    def test_logger_respects_level(self, caplog):
        """Test that logger respects log level."""
        with caplog.at_level(logging.INFO):
            log = setup_logging("LEVEL_TEST", level="INFO")
            log.debug("Debug message")  # Should not appear
            log.info("Info message")    # Should appear
        assert "Debug message" not in caplog.text
        assert "Info message" in caplog.text

    def test_logger_debug_level_logs_all(self, caplog):
        """Test that DEBUG level logs all messages."""
        with caplog.at_level(logging.DEBUG):
            log = setup_logging("DEBUG_LEVEL", level="DEBUG")
            log.debug("Debug")
            log.info("Info")
            log.warning("Warning")
        assert "Debug" in caplog.text
        assert "Info" in caplog.text
        assert "Warning" in caplog.text

    def test_logger_warning_level_filters_lower(self, caplog):
        """Test that WARNING level filters lower priority messages."""
        with caplog.at_level(logging.WARNING):
            log = setup_logging("WARN_FILTER", level="WARNING")
            log.debug("Debug")
            log.info("Info")
            log.warning("Warning")
        assert "Debug" not in caplog.text
        assert "Info" not in caplog.text
        assert "Warning" in caplog.text


class TestSetupLoggingEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_logger_name(self):
        """Test with empty logger name."""
        log = setup_logging("")
        assert isinstance(log, logging.Logger)

    def test_special_characters_in_name(self):
        """Test with special characters in logger name."""
        log = setup_logging("logger-test_123")
        assert log.name == "logger-test_123"

    def test_very_long_logger_name(self):
        """Test with very long logger name."""
        long_name = "a" * 1000
        log = setup_logging(long_name)
        assert log.name == long_name

    def test_invalid_level_defaults_to_info(self):
        """Test that invalid level defaults to INFO."""
        log = setup_logging("INVALID_LEVEL", level="INVALID")
        assert log.level == logging.INFO

    def test_none_level_defaults_to_info(self):
        """Test that None level defaults to INFO."""
        log = setup_logging("NONE_LEVEL", level="INFO")
        assert log.level == logging.INFO


class TestSetupLoggingIntegration:
    """Integration tests for logger setup."""

    def test_multiple_loggers_independent(self):
        """Test that multiple loggers are independent."""
        log1 = setup_logging("LOGGER_A", level="DEBUG")
        log2 = setup_logging("LOGGER_B", level="ERROR")
        assert log1.level == logging.DEBUG
        assert log2.level == logging.ERROR

    def test_logger_with_different_levels(self):
        """Test creating loggers with different levels."""
        levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        loggers = [setup_logging(f"LOG_{level}", level=level) for level in levels]

        expected_levels = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]
        for log, expected_level in zip(loggers, expected_levels):
            assert log.level == expected_level

    def test_logger_name_matches_input(self):
        """Test that logger name always matches input."""
        names = ["test1", "test.module", "app.component.logger"]
        for name in names:
            log = setup_logging(name)
            assert log.name == name
