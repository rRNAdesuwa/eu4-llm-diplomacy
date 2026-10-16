"""Independent entry-seed review only; not a full R51 semantic audit."""
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
BASE='work/reports/dynastic-trade-heir-static-20261015-r51/'
PINS={
 'manifest.json':'16591832bae45e96fb091bb0124a8646e93744685cdcf69f3ebd21b34d9d3e51',
 'owned-code.json':'aee9c9e4d697f0e39fbfa9b696a931664a6d40f9b7354a4611a812e7b04bcca5',
 'capture.json':'3cb6bc1e28e929d94be44fabd41ea1d3291a147f27f29a20164d35564b3734ee',
 'contract.json':'3613232fdca613cf0dc5a68a4f2398baee39277ca17d57721c4cdc8e372f4d94'}
OUT=ROOT/'work/reports/dynastic-trade-heir-callseed-root-20261015-r1'


def read(p):
    with p.open('rb') as f:b=f.read(2*1024*1024+1)
    assert 0<len(b)<=2*1024*1024
    return b


def pin(p):
    b=read(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def guard():
    out={BASE+n:pin(ROOT/(BASE+n)) for n in PINS}
    assert all(out[BASE+n]['sha256']==h for n,h in PINS.items())
    return out


def main():
    before=guard();OUT.mkdir(exist_ok=False)
    owned=json.loads(read(ROOT/(BASE+'owned-code.json')))
    capture=json.loads(read(ROOT/(BASE+'capture.json')))
    contract=json.loads(read(ROOT/(BASE+'contract.json')))
    raw=bytes.fromhex(owned['raw_hex']);assert len(raw)==4395
    assert owned['window']==['0x4fadc0','0x4fbeeb']
    assert capture['game_sha256']=='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
    assert capture['entry_rva']=='0x4fadc0' and capture['exact_pdata_begin'] is True
    assert capture['analysis']['instruction_count']==963
    rows=capture['analysis']['instructions']
    cursor=0x4fadc0
    for row in sorted(rows,key=lambda r:int(r['rva'],16)):
        addr=int(row['rva'],16);code=bytes.fromhex(row['bytes'])
        assert addr==cursor and raw[addr-0x4fadc0:addr-0x4fadc0+len(code)]==code
        cursor+=len(code)
    assert cursor==0x4fbeeb
    site=0x4fb5e1;target=0x30d200;row=next(r for r in rows if int(r['rva'],16)==site)
    code=bytes.fromhex(row['bytes']);assert len(code)==5 and code[0]==0xe8
    decoded=site+5+struct.unpack('<i',code[1:])[0]
    assert decoded==target and row['mnemonic']=='call' and int(row['operands'],16)==target
    consumption=contract['selected_stack_record']['consuming_call']
    assert int(consumption['site'],16)==site and int(consumption['target'],16)==target
    result=dict(schema='EU4-TRADE-HEIR-CALL-ENTRY-SEED-REVIEW/1',status='passed',
        scope='R51 owned bytes and exact direct CALL entry seed only; not a full R51 semantic or resource audit',
        source_pins=before,all_retained_rows_raw_consistent=True,entry_rva=hex(target),
        callsite_rva=hex(site),raw_hex=code.hex(),signed_rel32_target=hex(decoded),
        source_window=['0x4fadc0','0x4fbeeb'],game_sha256=capture['game_sha256'],
        caller_argument_comments_independently_authenticated=False,
        inherited_argument_comments=consumption,
        unknowns=['RCX/RDX/R8/R9/fifth argument comments remain R51 author observations, not this seed proof',
            'No target ABI, effect, country1298 write, class, ownership or lifetime has been proved',
            'R51 full independent semantic/store review remains outstanding'],
        full_R51_review_complete=False,source_before_after_equal=(guard()==before),
        operations=dict(PE_opens=0,decoder_calls=0,producer_or_analyzer_executed=0,game_process_accesses=0,native_game_calls=0,
            tests_run=0,requests_published=0,saves=0,reloads=0),
        native_ready=False,selected_effect_verified=False,reader_adoption_allowed=False,lease_verified=False)
    assert result['source_before_after_equal'] is True
    (OUT/'findings.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    manifest=dict(schema='EU4-ENTRY-SEED-FILE-MANIFEST/1',source_pins=before,
        files={'work/review_trade_heir_callseed_20261015.py':pin(Path(__file__)),
               (OUT/'findings.json').relative_to(ROOT).as_posix():pin(OUT/'findings.json')},native_ready=False)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='passed',findings=pin(OUT/'findings.json'),manifest=pin(OUT/'manifest.json'))))


if __name__=='__main__':main()
