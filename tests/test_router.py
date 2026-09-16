"""Model routing: every role resolves through settings, nothing is hardcoded."""

from agentic_rag.config import ROLES, Settings
from agentic_rag.llm.router import FAST_ROLES, ModelRouter


def test_one_model_means_one_client_for_every_role():
    router = ModelRouter(Settings(llm_provider="mock", llm_model="claude-sonnet-5@default"))
    assert not router.is_split()
    first = router.client_for("plan")
    for role in ROLES:
        assert router.model_for(role) == "claude-sonnet-5@default"
        assert router.client_for(role) is first


def test_two_tiers_split_mechanical_roles_from_the_writing_roles():
    router = ModelRouter(
        Settings(
            llm_provider="mock",
            llm_model="fallback",
            llm_model_fast="v4-flash",
            llm_model_deep="v4-pro",
        )
    )
    assert router.is_split()
    for role in ROLES:
        expected = "v4-flash" if role in FAST_ROLES else "v4-pro"
        assert router.model_for(role) == expected, role


def test_a_pinned_role_beats_the_tier():
    router = ModelRouter(
        Settings(
            llm_provider="mock",
            llm_model_fast="flash",
            llm_model_deep="pro",
            llm_role_models={"judge": "judge-only-model", "synthesize": "writer-model"},
        )
    )
    assert router.model_for("judge") == "judge-only-model"
    assert router.model_for("synthesize") == "writer-model"
    assert router.model_for("plan") == "flash"
    assert router.model_for("verify") == "pro"


def test_role_overrides_are_read_from_the_environment():
    import os

    os.environ["LLM_MODEL_VISION"] = "some-vision-model"
    os.environ["LLM_MODEL_FAST"] = "cheap"
    try:
        settings = Settings.from_env()
        assert settings.llm_role_models["vision"] == "some-vision-model"
        assert ModelRouter(settings).model_for("vision") == "some-vision-model"
        assert ModelRouter(settings).model_for("plan") == "cheap"
    finally:
        del os.environ["LLM_MODEL_VISION"]
        del os.environ["LLM_MODEL_FAST"]


def test_describe_covers_every_role():
    router = ModelRouter(Settings(llm_provider="mock"))
    described = router.describe()
    assert set(described) == set(ROLES)


def test_pipeline_uses_the_router_for_each_stage(tmp_path):
    from agentic_rag.pipeline import AgenticRAG

    rag = AgenticRAG(
        Settings(
            llm_provider="mock",
            search_provider="none",
            storage_dir=str(tmp_path / "storage"),
        )
    )
    assert rag.router.model_for("verify") == rag.router.model_for("synthesize")
    assert rag.verifier.llm is rag.llm  # one model, so the clients coincide
