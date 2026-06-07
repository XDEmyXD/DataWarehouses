from app.__init__ import create_app


def test_swagger_ui_endpoints():
    app = create_app()
    client = app.test_client()

    docs_resp = client.get("/api/docs")
    assert docs_resp.status_code == 200
    assert b"SwaggerUIBundle" in docs_resp.data

    openapi_resp = client.get("/api/openapi.json")
    assert openapi_resp.status_code == 200
    json_data = openapi_resp.get_json()
    assert json_data["openapi"] == "3.0.3"
    assert "/api/assets" in json_data["paths"]
