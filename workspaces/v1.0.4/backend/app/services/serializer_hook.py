from sqlalchemy import event
from sqlalchemy.orm import Session
from app.models.all_models import Project, Page, TextBlock
from app.services.project_serializer import save_project_json
import logging

logger = logging.getLogger("houmi-serializer-hook")

@event.listens_for(Session, 'before_commit')
def receive_before_commit(session):
    project_ids = set()
    
    # Union of new, dirty, and deleted objects
    all_objects = session.new.union(session.dirty).union(session.deleted)
    for obj in all_objects:
        if isinstance(obj, Project):
            project_ids.add(obj.id)
        elif isinstance(obj, Page):
            if obj.project_id:
                project_ids.add(obj.project_id)
        elif isinstance(obj, TextBlock):
            if obj.page:
                if obj.page.project_id:
                    project_ids.add(obj.page.project_id)
            elif obj.page_id:
                # Resolve project_id via query
                try:
                    page = session.query(Page).filter(Page.id == obj.page_id).first()
                    if page and page.project_id:
                        project_ids.add(page.project_id)
                except Exception:
                    pass
                    
    if project_ids:
        session.info['projects_to_serialize'] = project_ids

@event.listens_for(Session, 'after_commit')
def receive_after_commit(session):
    project_ids = session.info.pop('projects_to_serialize', None)
    if project_ids:
        for pid in project_ids:
            try:
                save_project_json(pid, session)
            except Exception as e:
                logger.error(f"Error serializing project {pid} after commit: {e}")
