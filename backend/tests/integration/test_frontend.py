"""The local interface uses the same origin; no npm server or CDN is needed."""


def test_frontend_and_local_assets_are_served(client):
    response = client.get('/')
    assert response.status_code == 200
    assert 'Lead Vision' in response.text
    assert '/assets/app.js' in response.text
    assert response.headers['cache-control'] == 'no-cache'
    for asset in ('shared/styles/app.css', 'app.js', 'shared/api.js', 'modules/agency/index.js', 'modules/processing/index.js'):
        assert client.get('/assets/' + asset).status_code == 200
    assert client.get('/docs').status_code == 200


def test_static_mount_cannot_read_backend_or_database(client):
    for path in ('/assets/../backend/.env', '/assets/%2e%2e/backend/app/main.py', '/assets/data/leadvision.sqlite3'):
        assert client.get(path).status_code == 404
