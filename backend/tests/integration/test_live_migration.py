import importlib
from uuid import uuid4
import pytest
from sqlalchemy import insert, select, func
from app.modules.foundation.database_base import SchemaVersion
from app.modules.foundation.database_session import Database
from app.modules.foundation.migration_runner import MIGRATIONS_DIR, migrate, SUPPORTED_SCHEMA_VERSION
from app.modules.foundation.hashing import content_hash
from app.modules.agency.agency_model import Agency
from app.modules.icp.icp_model import ICP, ICPVersion
from app.modules.campaigns.campaign_model import Campaign
from app.modules.leads.company_model import Company
from app.modules.leads.lead_model import Lead
from app.modules.processing.job_model import Job
from app.modules.processing.analysis_run_model import AnalysisRun
from app.modules.evidence.evidence_model import Evidence, SavedEvidenceUpload
from app.modules.scoring.score_model import ScoreRun, ScoreComponent


@pytest.mark.parametrize('broken', [False, True])
@pytest.mark.parametrize('starting_version', [11,12])
def test_populated_upgrade_preserves_saved_sources_jobs_scores_and_rolls_back(settings, monkeypatch, broken, starting_version):
    settings.data_dir.mkdir(); db = Database(settings)
    try:
        with db.engine.begin() as connection:
            SchemaVersion.__table__.create(connection)
            for source in sorted(MIGRATIONS_DIR.glob('*.py')):
                if not source.name[:3].isdigit() or int(source.name[:3]) > starting_version: continue
                importlib.import_module('app.modules.foundation.' + source.stem).upgrade(connection)
                connection.execute(insert(SchemaVersion).values(version=int(source.name[:3]),
                    checksum=content_hash(source.read_text(encoding='utf-8').encode()), applied_at='time'))
        with db.transaction() as session:
            agency = Agency(name='Existing agency'); session.add(agency); session.flush()
            profile = ICP(agency_id=agency.id,name='Existing ICP'); session.add(profile); session.flush()
            version = ICPVersion(icp_id=profile.id,version=1,config={},content_hash='a'*64,
                semantic_input_hash='b'*64,score_rule_version='weighted-fit-v1'); session.add(version);session.flush()
            profile.current_version_id = version.id
            campaign = Campaign(agency_id=agency.id,icp_id=profile.id,name='Existing campaign'); session.add(campaign)
            company = Company(normalized_domain='company.example'); session.add(company);session.flush()
            lead = Lead(campaign_id=campaign.id,company_id=company.id,company_name='Existing company',
                name_key='existing company',website='https://company.example',normalized_url='https://company.example/')
            session.add(lead);session.flush()
            job = Job(agency_id=agency.id,lead_id=lead.id,request_hash='a'*64,request_body={},
                input_snapshot={},idempotency_key='old',scope='analysis:'+lead.id);session.add(job);session.flush()
            run = AnalysisRun(job_id=job.id,lead_id=lead.id,icp_version_id=version.id,lead_input_revision=1,
                evidence_mode='uploaded',input_snapshot={},fingerprint='a'*64);session.add(run);session.flush()
            upload = SavedEvidenceUpload(lead_id=lead.id,token_hash='c'*64,source_mode='uploaded',state='attached',
                manifest={},attached_job_id=job.id,expires_at='time');session.add(upload);session.flush()
            evidence = Evidence(id=str(uuid4()),run_id=run.id,saved_upload_id=upload.id,kind='text',
                source_mode='uploaded',imported_at='time',metadata_json={'sha256':'preserved'})
            score = ScoreRun(id=str(uuid4()),run_id=run.id,lead_id=lead.id,result={'score':90},provenance={})
            session.add_all([evidence,score]);session.flush()
            session.add(ScoreComponent(id=str(uuid4()),score_id=score.id,name='industry',result={'value':100}))
        if broken:
            name='012_live_evidence' if starting_version==11 else '013_agency_knowledge'
            module = importlib.import_module('app.modules.foundation.'+name); original = module.upgrade
            def fail(connection): original(connection); raise RuntimeError('Injected failure')
            monkeypatch.setattr(module,'upgrade',fail)
            with pytest.raises(RuntimeError,match='Injected'): migrate(db.engine)
        else: assert migrate(db.engine) == SUPPORTED_SCHEMA_VERSION
        with db.sessions() as session:
            assert session.get(Job,job.id).request_hash=='a'*64
            assert session.get(AnalysisRun,run.id).job_id==job.id
            assert session.get(Evidence,evidence.id).metadata_json == {'sha256':'preserved'}
            assert session.get(ScoreRun,score.id).result == {'score':90}
            assert session.scalar(select(func.count()).select_from(ScoreComponent)) == 1
        with db.engine.connect() as connection:
            assert connection.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
            assert not connection.exec_driver_sql('PRAGMA foreign_key_check').all()
            assert connection.exec_driver_sql('SELECT max(version) FROM schema_versions').scalar() == (starting_version if broken else SUPPORTED_SCHEMA_VERSION)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError),db.transaction() as session:
            session.get(Job,job.id).request_hash='changed'
    finally: db.close()
