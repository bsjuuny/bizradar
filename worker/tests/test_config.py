from worker.config import Settings


def test_defaults_to_mock_mode_and_local_ollama():
    settings = Settings(_env_file=None)

    assert settings.data_mode == "mock"
    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.ollama_model == "qwen3:8b"
    assert settings.supabase_url is None


def test_live_mode_is_explicit_opt_in():
    settings = Settings(_env_file=None, data_mode="live")

    assert settings.data_mode == "live"
