from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.llm.client import LLMClient
from app.main import app, get_llm_client
from app.storage.db import get_session
from tests.unit.fakes import FakeAnthropicClient, FakeMessage, FakeTextBlock, FakeToolUseBlock, FakeUsage

DATASETS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "datasets"


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _scripted_pipeline_responses():
    return [
        FakeMessage(
            content=[
                FakeToolUseBlock(
                    id="plan_1",
                    name="submit_analysis_plan",
                    input={
                        "steps": [
                            {
                                "step_id": 1,
                                "operation": "calculate_sum",
                                "rationale": "Total revenue.",
                                "target_columns": ["revenue"],
                            }
                        ]
                    },
                )
            ],
            usage=FakeUsage(200, 50),
            stop_reason="tool_use",
        ),
        FakeMessage(
            content=[FakeToolUseBlock(id="tu_1", name="calculate_sum", input={"column": "revenue"})],
            usage=FakeUsage(150, 30),
            stop_reason="tool_use",
        ),
        FakeMessage(
            content=[FakeTextBlock(text="Total revenue computed.")], usage=FakeUsage(100, 20), stop_reason="end_turn"
        ),
        FakeMessage(
            content=[
                FakeToolUseBlock(
                    id="ev_1",
                    name="submit_evidence",
                    input={
                        "evidence_items": [
                            {"claim": "Total revenue is known.", "calculation_index": 0, "confidence": 0.9}
                        ]
                    },
                )
            ],
            usage=FakeUsage(100, 30),
            stop_reason="tool_use",
        ),
        FakeMessage(
            content=[
                FakeToolUseBlock(
                    id="ver_1",
                    name="submit_verification",
                    input={"status": "VERIFIED", "confidence": 0.9, "issues": []},
                )
            ],
            usage=FakeUsage(100, 20),
            stop_reason="tool_use",
        ),
        FakeMessage(
            content=[
                FakeToolUseBlock(
                    id="ins_1",
                    name="submit_insights",
                    input={
                        "insights": [
                            {
                                "verification_index": 0,
                                "title": "Total revenue",
                                "finding": "Total revenue is known.",
                                "business_significance": "Baseline metric for the business.",
                                "limitations": [],
                            }
                        ]
                    },
                )
            ],
            usage=FakeUsage(100, 20),
            stop_reason="tool_use",
        ),
        FakeMessage(
            content=[
                FakeToolUseBlock(
                    id="rec_1",
                    name="submit_recommendations",
                    input={
                        "recommendations": [
                            {
                                "insight_indices": [0],
                                "recommendation": "Track revenue monthly going forward.",
                                "expected_impact": "Better visibility into trends.",
                                "uncertainty": "None significant for this metric.",
                                "next_investigation": "n/a",
                            }
                        ]
                    },
                )
            ],
            usage=FakeUsage(100, 20),
            stop_reason="tool_use",
        ),
        FakeMessage(
            content=[FakeTextBlock(text="Total revenue has been computed and verified.")],
            usage=FakeUsage(100, 30),
            stop_reason="end_turn",
        ),
    ]


def test_upload_dataset_returns_real_profile(client):
    csv_bytes = (DATASETS_DIR / "01_sales_decline" / "data.csv").read_bytes()

    response = client.post("/api/datasets", files={"file": ("data.csv", csv_bytes, "text/csv")})

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["row_count"] == 216
    assert "region" in body["profile"]["columns"]


def test_upload_rejects_unsupported_file_type(client):
    response = client.post("/api/datasets", files={"file": ("data.json", b"{}", "application/json")})
    assert response.status_code == 400


def test_upload_rejects_empty_csv_with_clean_400(client):
    response = client.post("/api/datasets", files={"file": ("empty.csv", b"", "text/csv")})
    assert response.status_code == 400
    assert "Could not read dataset" in response.json()["detail"]


def test_upload_rejects_ragged_csv_with_clean_400(client):
    response = client.post("/api/datasets", files={"file": ("ragged.csv", b"a,b\n1,2\n3,4,5\n", "text/csv")})
    assert response.status_code == 400


def test_upload_rejects_corrupt_binary_with_clean_400(client):
    response = client.post("/api/datasets", files={"file": ("corrupt.csv", bytes(range(256)), "text/csv")})
    assert response.status_code == 400


def test_full_run_via_http_with_fake_llm(client):
    csv_bytes = (DATASETS_DIR / "01_sales_decline" / "data.csv").read_bytes()
    upload = client.post("/api/datasets", files={"file": ("data.csv", csv_bytes, "text/csv")})
    dataset_id = upload.json()["dataset_id"]

    fake = FakeAnthropicClient.with_responses(_scripted_pipeline_responses())
    app.dependency_overrides[get_llm_client] = lambda: LLMClient(api_client=fake, model="gemini-3.6-flash")

    response = client.post("/api/runs", params={"dataset_id": dataset_id, "question": "What is total revenue?"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["report"]["executive_summary"] == "Total revenue has been computed and verified."
    assert len(body["report"]["key_findings"]) == 1

    run_id = body["run_id"]
    status_response = client.get(f"/api/runs/{run_id}")
    assert status_response.status_code == 200
    stage_names = [s["stage_name"] for s in status_response.json()["stages"]]
    assert stage_names == [
        "profile", "plan", "analyst", "evidence", "verification", "insights", "recommendations", "report",
    ]


def test_run_with_unknown_dataset_returns_404(client):
    response = client.post("/api/runs", params={"dataset_id": "does-not-exist", "question": "Why?"})
    assert response.status_code == 404


def test_run_with_unknown_id_returns_404(client):
    response = client.get("/api/runs/does-not-exist")
    assert response.status_code == 404


def test_list_runs_returns_created_runs_newest_first(client):
    csv_bytes = (DATASETS_DIR / "01_sales_decline" / "data.csv").read_bytes()
    upload = client.post("/api/datasets", files={"file": ("data.csv", csv_bytes, "text/csv")})
    dataset_id = upload.json()["dataset_id"]

    fake = FakeAnthropicClient.with_responses(_scripted_pipeline_responses())
    app.dependency_overrides[get_llm_client] = lambda: LLMClient(api_client=fake, model="gemini-3.6-flash")
    run_response = client.post("/api/runs", params={"dataset_id": dataset_id, "question": "What is total revenue?"})
    run_id = run_response.json()["run_id"]

    listing = client.get("/api/runs")

    assert listing.status_code == 200
    runs = listing.json()
    assert any(r["run_id"] == run_id for r in runs)
    assert runs[0]["status"] == "COMPLETED"


def test_list_runs_empty_when_none_created(client):
    response = client.get("/api/runs")
    assert response.status_code == 200
    assert response.json() == []


def test_cors_allows_the_frontend_dev_origin(client):
    # Without CORSMiddleware, every browser request from the Next.js dev
    # server is silently blocked by the browser's CORS check while this
    # same request via TestClient/curl (neither enforces CORS) keeps
    # passing — this test is what actually catches that regression.
    response = client.get("/api/runs", headers={"Origin": "http://localhost:3000"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
