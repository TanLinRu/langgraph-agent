import pytest
import os
from unittest.mock import patch, MagicMock


class TestConfig:

    def test_initialization_config_from_config_module(self):
        """验证 InitializationConfig 从 config 模块正确导入"""
        from src.agent.config import InitializationConfig

        config = InitializationConfig()
        assert config.resume_on_startup is True
        assert config.load_recent_sessions == 5
        assert config.load_memory is True

    def test_context_initializer_uses_correct_config_type(self):
        """验证 ContextInitializer 使用正确的配置类型"""
        from src.agent.config import InitializationConfig
        from src.agent.context.initialization import ContextInitializer

        long_term_mock = patch("src.agent.context.long_term.LongTermManager")
        with long_term_mock:
            config = InitializationConfig(resume_on_startup=False)
            manager = MagicMock()
            initializer = ContextInitializer(manager, config)
            assert initializer.config == config
