import json
import uuid
from datetime import timedelta

import httpx
import pytest

from app.ai.vision import (
    VisionBadOutputError,
    VisionModelMissingError,
    VisionProvider,
    VisionRateLimitedError,
    VisionTimeoutError,
    VisionUnavailableError,
    parse_vision_output,
)
from app.core.config import Settings
from app.core.signed_refs import InvalidRefError, sign_ref, verify_ref


def test_valid_output_is_normalised() -> None:
    raw = json.dumps(
        {
            "items": [
                {
                    "name": " * Apple ",
                    "description": "red",
                    "alternatives": ["apple", "Pear", "Pear"],
                },
                {"name": "apple"},
            ],
            "notes": "ok",
            "extra": 1,
        }
    )
    out = parse_vision_output(raw)
    assert [i.name for i in out.items] == ["Apple"]  # duplicate dropped
    assert out.items[0].alternatives == ["Pear"]
    assert not hasattr(out.items[0], "confidence")


def test_fenced_json_is_accepted() -> None:
    assert (
        parse_vision_output('```json\n{"items": [{"name": "Rice"}]}\n```').items[0].name == "Rice"
    )


def test_empty_items_is_a_valid_answer() -> None:
    assert parse_vision_output('{"items": []}').items == []


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "not json",
        "[1,2]",
        '"str"',
        "{}",
        '{"items": "apple"}',
        '{"items": [{"name": ""}]}',
        '{"items": [{"description": "x"}]}',
        '{"items": [{"name": 5}]}',
        json.dumps({"items": [{"name": f"f{i}"} for i in range(16)]}),
        json.dumps({"items": [{"name": "x" * 200}]}),
    ],
)
def test_bad_output_is_rejected_not_repaired(raw: object) -> None:
    with pytest.raises(VisionBadOutputError):
        parse_vision_output(raw)


def test_control_characters_are_stripped() -> None:
    out = parse_vision_output(json.dumps({"items": [{"name": "Dal\u0000\n tadka"}]}))
    assert out.items[0].name == "Dal tadka"


# ---- providers via mock transport ----
def _ollama(handler: httpx.MockTransport) -> VisionProvider:
    from app.ai.factory import build_vision_provider

    s = Settings(ollama_enabled=True, ollama_vision_model="llava-test")
    return build_vision_provider(s, transport=handler)


def _png() -> bytes:
    from tests.imgs import make_image

    return make_image("PNG", (32, 32))


def test_ollama_success_and_never_asks_for_numbers() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": '{"items":[{"name":"Idli"}]}'}})

    p = _ollama(httpx.MockTransport(handler))
    assert p.identify(_png()).items[0].name == "Idli"
    assert p.info.external is False
    prompt = json.dumps(seen).lower()
    assert "do not estimate weights" in prompt  # the model is told not to guess quantities
    assert seen["stream"] is False


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(404, json={"error": "model not found"}), VisionModelMissingError),
        (httpx.Response(429), VisionRateLimitedError),
        (httpx.Response(500), VisionUnavailableError),
        (httpx.Response(200, json={"message": {"content": "banana"}}), VisionBadOutputError),
        (httpx.Response(200, json={"unexpected": 1}), VisionBadOutputError),
        (httpx.Response(200, text="<html>"), VisionBadOutputError),
    ],
)
def test_ollama_errors_map_to_typed_errors(
    response: httpx.Response, error: type[Exception]
) -> None:
    p = _ollama(httpx.MockTransport(lambda r: response))
    with pytest.raises(error):
        p.identify(_png())


def test_ollama_timeout_and_connection_errors() -> None:
    def timeout(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=req)

    def refused(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=req)

    with pytest.raises(VisionTimeoutError):
        _ollama(httpx.MockTransport(timeout)).identify(_png())
    with pytest.raises(VisionUnavailableError):
        _ollama(httpx.MockTransport(refused)).identify(_png())


def test_not_enabled_or_no_model_means_unavailable_and_no_fallback() -> None:
    from app.ai.factory import build_vision_provider

    with pytest.raises(VisionUnavailableError):
        build_vision_provider(Settings())
    with pytest.raises(VisionUnavailableError):
        build_vision_provider(Settings(ollama_enabled=True))


def test_external_provider_needs_explicit_opt_in() -> None:
    with pytest.raises(ValueError, match="(?i)external"):
        Settings(
            vision_provider="openai_compatible",
            vision_api_base_url="https://api.example.com/v1",
            vision_api_model="m",
        )


def _openai(
    handler: httpx.MockTransport, base: str = "https://api.example.com/v1"
) -> VisionProvider:
    from app.ai.factory import build_vision_provider

    s = Settings(
        vision_provider="openai_compatible",
        allow_external_ai_providers=True,
        vision_api_base_url=base,
        vision_api_model="m",
        vision_api_key="sk-test-secret",
    )
    return build_vision_provider(s, transport=handler)


def test_openai_compatible_sends_key_and_flags_external() -> None:
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers.get("authorization", "")
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"items":[{"name":"Roti"}]}'}}]}
        )

    p = _openai(httpx.MockTransport(handler))
    assert p.identify(_png()).items[0].name == "Roti"
    assert seen["auth"] == "Bearer sk-test-secret"
    assert p.info.external is True
    local = _openai(httpx.MockTransport(handler), "http://localhost:8080/v1")
    assert local.info.external is False


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(401), VisionUnavailableError),
        (httpx.Response(429), VisionRateLimitedError),
        (httpx.Response(200, json={"choices": []}), VisionBadOutputError),
        (
            httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]}),
            VisionBadOutputError,
        ),
    ],
)
def test_openai_errors_map_to_typed_errors(
    response: httpx.Response, error: type[Exception]
) -> None:
    with pytest.raises(error):
        _openai(httpx.MockTransport(lambda r: response)).identify(_png())


# ---- signed references ----
def _settings() -> Settings:
    return Settings()


def test_ref_round_trip_and_user_binding() -> None:
    s, u = _settings(), uuid.uuid4()
    token = sign_ref(s, "scan", u, {"a": 1})
    assert verify_ref(s, "scan", u, token) == {"a": 1}
    with pytest.raises(InvalidRefError):
        verify_ref(s, "scan", uuid.uuid4(), token)  # someone else's
    with pytest.raises(InvalidRefError):
        verify_ref(s, "food", u, token)  # wrong kind


def test_tampered_or_garbage_refs_rejected() -> None:
    s, u = _settings(), uuid.uuid4()
    token = sign_ref(s, "food", u, {"v": 100})
    body, _, sig = token.rpartition(".")
    for bad in (body + "." + sig[::-1], "x." + sig, "", "nodot", token[:-3] + "AAA"):
        with pytest.raises(InvalidRefError):
            verify_ref(s, "food", u, bad)


def test_expired_ref_rejected() -> None:
    s, u = _settings(), uuid.uuid4()
    short = s.model_copy(update={"signed_ref_ttl_minutes": -1})
    token = sign_ref(short, "scan", u, {"a": 1})
    with pytest.raises(InvalidRefError):
        verify_ref(short, "scan", u, token)
    _ = timedelta
