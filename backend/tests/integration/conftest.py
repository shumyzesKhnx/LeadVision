import pytest
from app.modules.processing.worker_main import Worker
from test_leads import setup_campaign, add_lead


@pytest.fixture
def job_lead(client):
    return add_lead(client, setup_campaign(client))


@pytest.fixture
def registered_worker(client, application, settings):
    with Worker(application.state.database, settings) as worker:
        yield worker
