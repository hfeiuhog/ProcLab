"""Reproducible synthetic fixture expansion. No real factory records are implied."""
import csv
import hashlib
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'

def save(name,value):
    (DATA/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    with (DATA/'batches.csv').open(encoding='utf-8',newline='') as f:
        reader=csv.DictReader(f)
        header=reader.fieldnames
        rows=[r for r in reader if r['batch_id'] in ('B-101','B-102','B-103')]
    labels={
      'B-101':dict(scenario='normal',expected_findings=0,expected_missing=0,split='demo'),
      'B-102':dict(scenario='multiple',expected_findings=6,expected_missing=0,split='demo'),
      'B-103':dict(scenario='missing',expected_findings=0,expected_missing=1,split='demo'),
    }
    scenarios=['normal','high_temperature','high_pressure','high_viscosity','multiple','missing','invalid','boundary','drift','unit_suspect']
    expected=[(0,0),(2,0),(2,0),(2,0),(6,0),(0,2),(0,2),(0,0),(1,0),(2,0)]
    rng=random.Random(20261020)
    for i in range(60):
        batch=f'B-{201+i}'
        case=i%10
        scenario=scenarios[case]
        labels[batch]=dict(scenario=scenario,expected_findings=expected[case][0],expected_missing=expected[case][1],
                           split='holdout' if i//10==5 else 'development')
        for j in range(8):
            row=dict(batch_id=batch,row_id=str(len(rows)+2),temperature_c=f'{rng.uniform(190,212):.2f}',
                     pressure_mpa=f'{rng.uniform(1.9,2.1):.3f}',viscosity_pas=f'{rng.uniform(42,48):.2f}',
                     device_id=f'LINE-{chr(65+i%3)}',measured_at=(datetime(2026,9,4)+timedelta(hours=i*2,minutes=j*5)).isoformat())
            if j in (3,6):
                if case in (1,4): row['temperature_c']=str(226+j)
                if case in (2,4): row['pressure_mpa']=str(2.3+j/100)
                if case in (3,4): row['viscosity_pas']=str(52+j)
                if case==5: row['pressure_mpa' if j==3 else 'viscosity_pas']=''
                if case==6: row['temperature_c' if j==3 else 'pressure_mpa']='NaN' if j==3 else 'sensor_error'
                if case==9: row['pressure_mpa']=str(2000+j*10)
            if case==7 and j in (2,5):
                row.update(temperature_c='180' if j==2 else '220',pressure_mpa='1.8' if j==2 else '2.2',viscosity_pas='40' if j==2 else '50')
            if case==8: row['temperature_c']=str(190+j*5)
            rows.append(row)
    with (DATA/'batches.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=header); w.writeheader(); w.writerows(rows)
    save('batch_labels.json',labels)
    save('dataset_manifest.json',dict(measurement_rows=len(rows),batches=len(labels),scenarios=scenarios,seed=20261020,
        origin='synthetic',units={'temperature_c':'℃','pressure_mpa':'MPa','viscosity_pas':'Pa·s'},
        split_policy='整批划分；B-251至B-260为保留验收集，各含一种情形；保留集并非真实外部泛化测试。',
        holdout_batches=[k for k,v in labels.items() if v['split']=='holdout'],
        warning='所有测量与限值均为自制模拟，不是产线数据；unit_suspect只代表量级异常，工具不自动推断或转换单位。',
        sha256=hashlib.sha256((DATA/'batches.csv').read_bytes()).hexdigest()))
    print(json.dumps({'measurement_rows':len(rows),'batches':len(labels),'scenarios':len(scenarios),'holdout':10},ensure_ascii=False))
if __name__=='__main__': main()
