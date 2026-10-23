"""Explicit local-only administrator reset from private config. Never for ECS."""
from pathlib import Path
from sqlalchemy import update,delete
from sqlalchemy.engine import make_url
from app.config import Settings
from app.control import ControlPlane,users,sessions
from app.store import TaskStore

def validate_local_target(settings):
    if settings.app_env!='development':raise ValueError('Local reset requires development environment')
    if settings.database_url:
        url=make_url(settings.database_url)
        if url.get_backend_name()!='sqlite' and url.host not in ('127.0.0.1','localhost','::1'):
            raise ValueError('Local reset refuses remote database hosts')

def main():
    settings=Settings();validate_local_target(settings);settings.check()
    store=TaskStore(Path(settings.runtime_dir)/'tasks.db',settings.database_url)
    try:
        control=ControlPlane(store.engine,settings)
        with store.engine.begin() as cn:
            cn.execute(update(users).where(users.c.id=='admin').values(username=settings.admin_username,password_hash=settings.admin_password_hash,active=1))
            cn.execute(delete(sessions).where(sessions.c.user_id=='admin'))
        control.audit('admin','admin','local_admin_reset','admin',{'environment':'development'})
    finally:store.close()
    print('Local administrator reset from private configuration; existing local admin sessions revoked. Cloud unchanged.')
if __name__=='__main__':main()
