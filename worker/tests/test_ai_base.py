import pytest

from worker.ai.base import AIProvider


def test_ai_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        AIProvider()
