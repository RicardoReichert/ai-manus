"""Unit tests for the built-in model capability catalog.

Pure unit tests — no server, no DB. The catalog is what spares an admin from
having to know a model's tool-calling quirks: registering "qwen3-4b" should
automatically produce a small-model profile.
"""
from app.domain.models.model_capabilities import ModelCapabilities
from app.infrastructure.external.llm.model_catalog import (
    lookup_capabilities,
    is_known_model,
)


class TestSmallModels:
    def test_qwen3_4b_gets_a_small_model_profile(self):
        caps = lookup_capabilities("qwen3-4b-instruct-2507")
        assert caps.supports_native_tools is True  # Qwen3 has strong native tool calling
        assert caps.max_tools is not None and caps.max_tools <= 12
        assert caps.context_window is not None

    def test_gemma_4_e4b_strips_thinking_from_history(self):
        """Google documents this quirk explicitly for agentic multi-turn use."""
        caps = lookup_capabilities("gemma-4-e4b-it")
        assert caps.strip_thinking_from_history is True
        assert caps.supports_native_tools is True
        assert caps.max_tools is not None and caps.max_tools <= 12
        assert caps.context_window == 128000

    def test_phi_4_mini_is_recognized_as_small(self):
        caps = lookup_capabilities("phi-4-mini-instruct")
        assert caps.max_tools is not None and caps.max_tools <= 12

    def test_small_models_are_flagged_constrained(self):
        for model in ("qwen3-4b", "gemma-4-e4b-it", "phi-4-mini"):
            assert lookup_capabilities(model).is_constrained is True, model


class TestLargeModels:
    def test_gpt_4o_is_unconstrained(self):
        caps = lookup_capabilities("gpt-4o")
        assert caps.max_tools is None
        assert caps.needs_guided_decoding is False
        assert caps.is_constrained is False

    def test_gemini_25_flash_is_unconstrained(self):
        caps = lookup_capabilities("gemini-2.5-flash")
        assert caps.max_tools is None
        assert caps.is_constrained is False


class TestMatching:
    def test_matching_is_case_insensitive(self):
        assert lookup_capabilities("Qwen3-4B-Instruct").max_tools is not None

    def test_provider_prefix_is_ignored(self):
        """OpenRouter-style ids carry a vendor prefix."""
        caps = lookup_capabilities("google/gemma-4-e4b-it")
        assert caps.strip_thinking_from_history is True

    def test_quantization_and_tag_suffixes_still_match(self):
        """Local runtimes append tags/quant suffixes to the base model name."""
        for variant in (
            "qwen3-4b-instruct-2507-q4_k_m",
            "qwen3-4b:latest",
            "qwen3-4b-instruct-gguf",
        ):
            assert lookup_capabilities(variant).max_tools is not None, variant

    def test_is_known_model_distinguishes_catalog_hits(self):
        assert is_known_model("gpt-4o") is True
        assert is_known_model("some-bespoke-finetune-v3") is False


class TestUnknownModels:
    def test_unknown_remote_model_keeps_full_capability(self):
        """No regression: an unrecognized hosted model behaves as before."""
        caps = lookup_capabilities("some-bespoke-finetune-v3")
        assert caps == ModelCapabilities()
        assert caps.max_tools is None
        assert caps.is_constrained is False

    def test_unknown_local_model_gets_a_conservative_profile(self):
        """A local endpoint is far more likely to be small/quantized."""
        caps = lookup_capabilities("some-bespoke-finetune-v3", is_local=True)
        assert caps.max_tools is not None
        assert caps.is_constrained is True

    def test_known_model_ignores_the_is_local_hint(self):
        """An explicitly catalogued model wins over the local heuristic."""
        assert lookup_capabilities("gpt-4o", is_local=True).max_tools is None


class TestSizeInference:
    """A parameter-count tag must beat the crude 'local means small' guess."""

    def test_uncatalogued_local_70b_is_not_treated_as_small(self):
        caps = lookup_capabilities("llama-3.1-70b-instruct", is_local=True)
        assert caps.max_tools is None, "a local 70B must not be crippled to 8 tools"
        assert caps.is_constrained is False

    def test_uncatalogued_local_7b_is_treated_as_small(self):
        caps = lookup_capabilities("mistral-7b-instruct", is_local=True)
        assert caps.max_tools is not None
        assert caps.needs_guided_decoding is True

    def test_size_is_read_even_without_the_local_hint(self):
        assert lookup_capabilities("mistral-7b-instruct").max_tools is not None

    def test_largest_number_in_the_name_wins(self):
        """'llama-3.1-70b' must read 70, not the 3.1 version number."""
        assert lookup_capabilities("llama-3.1-70b").max_tools is None

    def test_decimal_sizes_are_understood(self):
        assert lookup_capabilities("phi-3.8b-mini").max_tools is not None

    def test_size_inference_does_not_count_as_catalogued(self):
        """It is a heuristic, so the UI must not claim auto-detection."""
        assert is_known_model("mistral-7b-instruct") is False
