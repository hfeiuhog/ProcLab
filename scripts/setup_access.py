"""Provision private account configuration. Passwords stay in the local private .env."""
from pathlib import Path
import secrets
import os
import argparse
import getpass
from dotenv import dotenv_values
from app.control import password_hash


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--server',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    path=root/'.env'
    values=dict(dotenv_values(path if path.exists() else root/'.env.example'))
    for prefix,username in [('ADMIN','admin'),('HR','hr')]:
        values.setdefault(prefix+'_USERNAME',username)
        if not values.get(prefix+'_PASSWORD_HASH'):
            password=getpass.getpass(username+' initial password (12+ characters): ') if args.server else secrets.token_urlsafe(18)
            if len(password)<12:raise ValueError('Password requires 12+ characters')
            values[prefix+'_PASSWORD_HASH']=password_hash(password)
            # Owner handoff only. These two fields are NOT sent to the ECS.
            if not args.server:values[prefix+'_LOGIN_PASSWORD']=password
    values.update(AUTH_ENABLED='true',SESSION_TTL_SECONDS='43200',DEMO_DAILY_TASKS='30',
                  DEMO_GLOBAL_DAILY_TASKS='100',HARNESS_MAX_TOOL_CALLS='12',HARNESS_TIMEOUT_SECONDS='180',
                  HARNESS_MAX_REPAIRS='2',APP_IMAGE='proclab:3.0.0')
    values['LOCAL_TEMP_DIR']=str(root / Path(values.get('RUNTIME_DIR') or 'runtime') / 'tmp')
    path.write_text('\n'.join(f'{k}={v or ""}' for k,v in values.items())+'\n',encoding='utf-8')
    if os.name!='nt':path.chmod(0o600)
    Path(values['LOCAL_TEMP_DIR']).mkdir(parents=True,exist_ok=True)
    print('Account/password login enabled; no credentials printed. Local handoff passwords stay in the private .env; --server accepts hidden passwords without storing their plaintext.')

if __name__=='__main__': main()
