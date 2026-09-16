from agentic_rag.config import Settings
from agentic_rag.core.types import INSUFFICIENT_ANSWER, Evidence
from agentic_rag.llm.mock import MockLLM
from agentic_rag.verification.verifier import Verifier, split_claims


def _evidence(text):
    return Evidence(
        id="e1", text=text, source_type="vector", source_ref="doc.md#chunk0",
        title="Doc", tool_name="vector_search",
    )


def _verifier(min_groundedness=0.7):
    return Verifier(MockLLM(), Settings(verifier_mode="lexical", min_groundedness=min_groundedness))


def test_trailing_citation_fragments_merge_into_previous_claim():
    claims = split_claims("The Atlas P2 carries up to 450 kg. [1]")
    assert len(claims) == 1
    assert claims[0][1] == [1]


def test_supported_extractive_answer_passes():
    evidence = [_evidence("The Atlas P2 carries up to 450 kg on its standard load deck.")]
    report = _verifier().verify(
        "What is the payload?", "The Atlas P2 carries up to 450 kg on its standard load deck. [1]", evidence
    )
    assert report.passed
    assert report.groundedness == 1.0
    assert report.citation_coverage == 1.0


def test_fabricated_claim_fails_verification():
    evidence = [_evidence("The Atlas P2 carries up to 450 kg on its standard load deck.")]
    report = _verifier().verify(
        "How fast is it?", "The Atlas P2 flies at 900 kilometres per hour through the warehouse. [1]", evidence
    )
    assert not report.passed
    assert report.groundedness == 0.0
    assert not report.verdicts[0].supported


def test_honest_insufficient_answer_passes():
    report = _verifier().verify("Unknown topic?", INSUFFICIENT_ANSWER, [])
    assert report.passed
