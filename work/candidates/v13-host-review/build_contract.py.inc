# This block is inserted into the independent v13 protocol module.
def record_build(root=ROOT, output=OUTPUT):
    root,output=Path(root),Path(output)
    dll=output/DLL_NAME
    require(dll.is_file(),'Successful DLL build is required first')
    require(not (output/'build.json').exists(),'Build manifest exists; formal v13 build may not be overwritten')
    require(not any(output.glob('session-*')),'Refuse recording a used v13 runtime')
    native={name:file_hash(root/name) for name in SOURCES}
    require(native==EXPECTED_NATIVE_SOURCES,'Native sources differ from the fixed reviewed v13 candidate')
    support={name:file_hash(root/name) for name in SUPPORT_SOURCES}
    require(support==EXPECTED_SUPPORT_SOURCES,'Shared host support differs from reviewed inputs')
    speed_flags=re.findall(r'static constexpr bool running_speed_enabled = (true|false);',
        read_bounded(root/'work/native/v13/research-lab-1375.cpp',1024*1024).decode())
    require(speed_flags==['true'],'Reviewed v13 speed lease gate changed')
    manifest={'schema_version':2,'purpose':PURPOSE,'game_sha256':LOCAL_SHA256,
        'built_at_utc':datetime.now(timezone.utc).isoformat(),'dll_sha256':file_hash(dll),
        'source_sha256':native,'host_source_sha256':{name:file_hash(root/name) for name in HOST_SOURCES},
        'support_source_sha256':support,'native_candidate_review_sha256':NATIVE_REVIEW_SHA256,
        'owned_peace_stage_contract':OWNED_PEACE_STAGE_CONTRACT,
        'runtime_verified':False,'production_backend_registered':False,'fixture_profile':fixture_profile(root),
        'lease_duration_ms':5000,'lease_max_raw_date_delta':48,'requires_exact_process_external_watchdog':True,
        'running_speed_enabled':True}
    publish_exclusive(output/'build.json',(canonical(manifest)+'\n').encode())
    return manifest

def verify_build(root=ROOT, output=OUTPUT):
    root,output=Path(root),Path(output)
    raw=read_bounded(output/'build.json',65536)
    manifest=decode_json(raw.decode())
    require(isinstance(manifest,dict) and set(manifest)=={'schema_version','purpose','game_sha256','built_at_utc',
        'dll_sha256','source_sha256','host_source_sha256','support_source_sha256','native_candidate_review_sha256',
        'owned_peace_stage_contract','runtime_verified','production_backend_registered','fixture_profile',
        'lease_duration_ms','lease_max_raw_date_delta','requires_exact_process_external_watchdog','running_speed_enabled'},
        'Unexpected v13 build manifest schema')
    require(type(manifest['schema_version']) is int and manifest['schema_version']==2
        and manifest['purpose']==PURPOSE and manifest['game_sha256']==LOCAL_SHA256
        and manifest['runtime_verified'] is False and manifest['production_backend_registered'] is False
        and manifest['native_candidate_review_sha256']==NATIVE_REVIEW_SHA256
        and canonical(manifest['owned_peace_stage_contract'])==canonical(OWNED_PEACE_STAGE_CONTRACT),
        'Manifest differs from fixed v13 four-stage research contract')
    require(type(manifest['lease_duration_ms']) is int and manifest['lease_duration_ms']==5000
        and type(manifest['lease_max_raw_date_delta']) is int and manifest['lease_max_raw_date_delta']==48
        and manifest['requires_exact_process_external_watchdog'] is True and manifest['running_speed_enabled'] is True,
        'Manifest differs from bounded speed lease contract')
    require(manifest['source_sha256']==EXPECTED_NATIVE_SOURCES and manifest['support_source_sha256']==EXPECTED_SUPPORT_SOURCES,
        'Native or shared support source pin differs from reviewed candidate')
    require(isinstance(manifest['host_source_sha256'],dict) and set(manifest['host_source_sha256'])==set(HOST_SOURCES),
        'v13 host source manifest is incomplete')
    for section in ('source_sha256','host_source_sha256','support_source_sha256'):
        for name,digest in manifest[section].items():
            require(file_hash(root/name)==digest,'Source changed after build: '+name)
    require(manifest['fixture_profile']==fixture_profile(root),'Fixture differs from fixed reviewed definitions')
    require(file_hash(output/DLL_NAME)==manifest['dll_sha256'],'DLL changed after build')
    return manifest,hashlib.sha256(raw).hexdigest()

