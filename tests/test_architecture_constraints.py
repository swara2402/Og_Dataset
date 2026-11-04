from pathlib import Path

from backend.app.core.config import Settings


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_dataset_has_one_canonical_location():
    assert (ROOT / "knowledge_base/rules/master_rules.json").is_file()
    assert (ROOT / "knowledge_base/rules/adaptive_editing_policy.json").is_file()
    assert (ROOT / "knowledge_base/datasets/examples.jsonl").is_file()
    assert not (ROOT / "backend/app/rules").exists()
    assert not (ROOT / "backend/app/datasets").exists()
    assert not (ROOT / "rules").exists()


def test_ollama_and_hosted_model_configuration_are_absent():
    fields = Settings.model_fields
    assert not any("ollama" in name.lower() for name in fields)
    assert not (ROOT / "ollama_provider.py").exists()
    assert not (ROOT / "hosted_gateway.py").exists()
    assert not (ROOT / "backend/app/providers/ollama_adapter.py").exists()
    assert not (ROOT / "backend/app/providers/ollama_suggestion_engine.py").exists()


def test_paragraph_analysis_contract_exposes_only_deterministic_and_optional_spacy():
    from backend.app.api.router import ParagraphAnalysisRequest

    fields = ParagraphAnalysisRequest.model_fields
    assert "include_nlp" in fields
    assert "include_local_llm" not in fields

def test_public_web_originality_is_absent_from_offline_core():
    from backend.app.api.router import api_router

    paths = {route.path for route in api_router.routes}
    assert "/originality/check" not in paths
    assert "enable_web_originality" not in Settings.model_fields
    assert not (ROOT / "backend/app/originality").exists()
    frontend_api = (ROOT / "frontend/src/contexts/APIContext.tsx").read_text(encoding="utf-8")
    assert "runOriginality" not in frontend_api
    assert "/originality/check" not in frontend_api

def test_backend_application_has_no_outbound_http_client_imports():
    import ast

    blocked_roots = {"requests", "aiohttp", "httpx"}
    blocked_modules = {"urllib.request", "socket"}
    offenders = []
    for source in (ROOT / "backend/app").rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in blocked_roots or alias.name in blocked_modules:
                        offenders.append(f"{source.relative_to(ROOT)}:{node.lineno}:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in blocked_roots or node.module in blocked_modules:
                    offenders.append(f"{source.relative_to(ROOT)}:{node.lineno}:{node.module}")
    assert offenders == []
