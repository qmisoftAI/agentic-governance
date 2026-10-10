from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_offline_compose_and_docs():
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "internal: true" in compose
    assert "outbound" not in compose
    assert (ROOT / "docs/OFFLINE_DEPLOYMENT.md").exists()
    assert (ROOT / "docs/FINDINGS_AND_DECISIONS.md").exists()
    assert '"local-demo"' in (ROOT / "governance/main.py").read_text()
