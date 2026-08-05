import json
import pytest
from unittest.mock import MagicMock, patch

from extensions.llm import LLM, LLMResult

pytestmark = pytest.mark.unit


def _fake_urlopen_response(payload):
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(payload).encode('utf-8')
    return mock_response


def test_llm_defaults_model_name_from_config(monkeypatch):
    import extensions.llm as llm_module
    monkeypatch.setattr(llm_module.config, 'OLLAMA_MODEL', 'configured-model')

    llm = LLM()

    assert llm.model_name == 'configured-model'


def test_llm_explicit_model_name_overrides_config(monkeypatch):
    import extensions.llm as llm_module
    monkeypatch.setattr(llm_module.config, 'OLLAMA_MODEL', 'configured-model')

    llm = LLM(model_name='explicit-model')

    assert llm.model_name == 'explicit-model'


def test_generate_response_posts_to_configured_ollama_base_url(monkeypatch):
    """The endpoint must be built from config.OLLAMA_BASE_URL at call time,
    not a hardcoded localhost -- otherwise OLLAMA_BASE_URL overrides (as
    ollama_service.py already respects) would be silently ignored here."""
    import extensions.llm as llm_module
    monkeypatch.setattr(llm_module.config, 'OLLAMA_BASE_URL', 'http://ollama.example.com:11434')

    llm = LLM(model_name='test-model')
    payload = {'response': 'ok', 'done': True}

    with patch.object(llm_module.request, 'urlopen',
                       return_value=_fake_urlopen_response(payload)) as mock_urlopen:
        llm.generate_response('hello')

    request_obj = mock_urlopen.call_args.args[0]
    assert request_obj.full_url == 'http://ollama.example.com:11434/api/generate'


def test_generate_response_sends_configured_num_ctx(monkeypatch):
    """Without num_ctx, Ollama silently falls back to the model's own
    default context window, which can be too small for a large prompt to
    actually fit -- num_ctx must be sent explicitly, from config, on every
    call."""
    import extensions.llm as llm_module
    monkeypatch.setattr(llm_module.config, 'OLLAMA_NUM_CTX', 16384)

    llm = LLM(model_name='test-model')
    payload = {'response': 'ok', 'done': True}

    with patch.object(llm_module.request, 'urlopen',
                       return_value=_fake_urlopen_response(payload)) as mock_urlopen:
        llm.generate_response('hello')

    request_obj = mock_urlopen.call_args.args[0]
    sent_body = json.loads(request_obj.data.decode('utf-8'))
    assert sent_body['options']['num_ctx'] == 16384


def test_get_json_attr_fuzzy_matches_key_via_utils_is_similar_strings():
    """Regression test: _get_json_attr must call an actual method on Utils
    (is_similar_strings), not a name that doesn't exist on that class."""
    result = LLMResult(
        response='{"title": "Hello"}', context=None, context_provided=False,
        created_at='', done=True, done_reason='', total_duration=0, load_duration=0,
        prompt_eval_count=0, prompt_eval_duration=0, eval_count=0, eval_duration=0,
    )

    matched = result._get_json_attr('titles')  # deliberate near-miss (edit distance 1 from 'title')

    assert matched is not None
    assert matched.response == 'Hello'


def test_get_json_dict_returns_whole_parsed_object():
    result = LLMResult(
        response='```json\n{"title": "A", "reason": "B"}\n```', context=None, context_provided=False,
        created_at='', done=True, done_reason='', total_duration=0, load_duration=0,
        prompt_eval_count=0, prompt_eval_duration=0, eval_count=0, eval_duration=0,
    )

    assert result.get_json_dict() == {'title': 'A', 'reason': 'B'}
