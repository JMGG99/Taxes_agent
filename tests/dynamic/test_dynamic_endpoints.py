import pytest


async def test_list_pdfs_returns_expected_shape(client):
    r = await client.get("/dynamic-pdfs")
    assert r.status_code == 200
    body = r.json()
    assert "slots_used" in body
    assert "pdfs" in body
    assert isinstance(body["pdfs"], list)


async def test_get_records_unknown_hash_returns_404(client):
    r = await client.get("/dynamic-pdfs/000000000000/records")
    assert r.status_code == 404


async def test_delete_without_key_returns_422(client):
    r = await client.delete("/dynamic-pdfs/abc123")
    assert r.status_code == 422


async def test_delete_with_wrong_key_returns_401(client):
    r = await client.delete("/dynamic-pdfs/abc123", params={"key": "wrong"})
    assert r.status_code == 401


async def test_upload_non_pdf_returns_400(client):
    r = await client.post(
        "/upload-pdfs",
        files={"file": ("test.txt", b"not a pdf", "text/plain")},
    )
    assert r.status_code == 400
