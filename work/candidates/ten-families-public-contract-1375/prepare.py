from pathlib import Path
import argparse,hashlib,json
import generate
HERE=Path(__file__).resolve().parent
PIN_SHA='af348d9068d2740ea0784d25609071d3123cc340e32285483a68c712bbe6a54d'
def check():
    assert hashlib.sha256((HERE/'input-pins.json').read_bytes()).hexdigest()==PIN_SHA
    pins=generate.verify_inputs();assert generate.canonical(generate.build())==(HERE/'contract.json').read_bytes()
    index=json.loads((HERE/'source-index.json').read_text(encoding='utf-8'));assert index['input_pins_sha256']==PIN_SHA
    assert len(index['sources'])<=12
    for name,pin in index['sources'].items():
        path=(HERE/name).resolve();assert path.is_relative_to(HERE)
        raw=generate.read(path,131072);assert pin=={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    return {'checked':True,'families':10,'source_inputs':len(pins),'new_decode_bytes':0,'production_ready':False}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true',required=True);p.parse_args();print(json.dumps(check(),sort_keys=True))
