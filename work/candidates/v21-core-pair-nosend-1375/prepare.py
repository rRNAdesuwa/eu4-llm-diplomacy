"""Freeze six selected profiles from pinned static evidence; no old script import."""
import json
import re
import sys
from validate import HERE, ROOT, read, inputs, own, seal


def registry():
    inputs()
    parent=json.loads(read(ROOT/'work/candidates/v20-typed-family-dispatch-plan-1375/abi-registry.json'))
    names=['vassalaction','royal_marriage','improve_relation','guaranteeaction','spy_network']
    rows=[x for x in parent['research_families'] if x['family'] in names]
    rows.sort(key=lambda row:names.index(row['family']))
    curry=json.loads(read(ROOT/'work/candidates/curry-favors-contract-1375/contract.json'))
    rows.append({'family':'curry_favors','token':'0x3acc','size_bytes':64,'vtable_rva':'0x1c7aef8',
        'clone_rva':'0x5ae2b0','destructor_rva':'0x129450','mode_setter_rva':'0x4e99d0',
        'family_local_0x80_rva':'0x5ade60','family_full_0x88_rva':'0x5ae110',
        'modes':[{'protocol_id':k,'native_value':v['value']} for k,v in curry['actions'].items()],
        'full_preview_evidence':'sealed_normal_caller_static_not_runtime',
        'extra_and_cancel_contract':['both modes envoy=-1; stop requires current outgoing relation/mission',
            'DLC/TLS/script permission is not established by synthetic model']})
    source=read(HERE/'pair_component.cpp').decode('utf-8')
    parsed=re.findall(r'\{Family::(\w+),(0x[0-9a-f]+),(0x[0-9a-f]+),(0x[0-9a-f]+),(0x[0-9a-f]+),(0x[0-9a-f]+),(0x[0-9a-f]+),(0x[0-9a-f]+),(0x[0-9a-f]+),FullCallerEvidence::(\w+)\}',source)
    assert len(parsed)==6
    result=[]
    for row,code in zip(rows,parsed):
        actual=[int(x,16) for x in code[1:9]]
        expected=[int(row['token'],16),row['size_bytes']]+[int(row[k],16) for k in
            ('vtable_rva','clone_rva','destructor_rva','mode_setter_rva','family_local_0x80_rva','family_full_0x88_rva')]
        assert actual==expected,(row['family'],actual,expected)
        result.append({'family':row['family'],'cpp_family':code[0],'token':row['token'],'size_bytes':row['size_bytes'],
            'vtable_rva':row['vtable_rva'],'clone_rva':row['clone_rva'],'destructor_rva':row['destructor_rva'],
            'setter_rva':row['mode_setter_rva'],'local80_rva':row['family_local_0x80_rva'],'full88_rva':row['family_full_0x88_rva'],
            'modes':row['modes'],'full_caller_evidence':code[9],'constraints':row['extra_and_cancel_contract'],
            'native_ready':False,'runtime_verified':False,'production_ready':False})
    return {'schema_version':1,'private_only':True,'families':result,
        'factory_rva':'0x35d210','factory_argument2':'NULL','wrapper_rva':'0x4e9930','command_gate_rva':'0x4e8630',
        'command_size_bytes':88,'command_vtable_rva':'0x1c814b0','command_destructor_rva':'0x4e7470',
        'action_dtor_flag':1,'command_dtor_flag':1,'full88_text':'NULL','full88_option':False,
        'generic_4e9d00_is_full88':False,'profile_runtime_authorization':False,
        'spy_reader_bounds':{'envoys':256,'tasks':1024,'read_calls_per_pass':8192,'bytes_per_read':8},
        'source_scope':'sealed static file pins; no new decode, no actual process or caller validation'}


def main():
    expected=registry()
    path=HERE/'profile-registry.json'
    if '--check' in sys.argv:
        assert json.loads(read(path))==expected
        assert json.loads(read(HERE/'source-index.json'))==own()
    elif '--index-only' in sys.argv:
        assert json.loads(read(path))==expected
        seal(HERE/'source-index.json',own())
    else:
        seal(path,expected)
        seal(HERE/'source-index.json',own())
    print('registry profiles=6 modes=12 static_only runtime_verified=false')


if __name__=='__main__':main()
