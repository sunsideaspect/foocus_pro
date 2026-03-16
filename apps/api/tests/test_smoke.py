def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_character_and_photo_job_flow(client):
    character_response = client.post(
        "/characters",
        json={
            "name": "Test Character",
            "description": "Smoke profile",
            "references": ["https://example.com/ref.jpg"],
        },
    )
    assert character_response.status_code == 200
    character_id = character_response.json()["id"]

    payload = {
        "character_id": character_id,
        "prompt": "photorealistic portrait",
        "negative_prompt": "",
        "model": "default",
        "cfg_scale": 7.0,
        "steps": 28,
        "seed": 42,
        "idempotency_key": "smoke-1",
    }
    first_job = client.post("/jobs/photo", json=payload)
    assert first_job.status_code == 200
    first_job_id = first_job.json()["id"]
    assert first_job.json()["status"] == "queued"

    second_job = client.post("/jobs/photo", json=payload)
    assert second_job.status_code == 200
    assert second_job.json()["id"] == first_job_id

    status_response = client.get(f"/jobs/{first_job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["job_type"] == "photo"
