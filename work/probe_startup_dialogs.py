"""Bounded, read-only startup dialog inspection for the verified executable.

The probe follows known game/UI globals and a bounded UI object graph.
Startup waits never scan the process private heap.
"""
from pathlib import Path

source_path = Path(__file__).with_name("probe_native_state.py")
source = source_path.read_text(encoding="utf-8")
body = r'''
        import os
        target_vtable=base+0x1d57328

        class SYSTEM_INFO(C.Structure):
            _fields_=[('wProcessorArchitecture',W.WORD),('wReserved',W.WORD),
                      ('dwPageSize',W.DWORD),('lpMinimumApplicationAddress',C.c_void_p),
                      ('lpMaximumApplicationAddress',C.c_void_p),
                      ('dwActiveProcessorMask',C.c_size_t),('dwNumberOfProcessors',W.DWORD),
                      ('dwProcessorType',W.DWORD),('dwAllocationGranularity',W.DWORD),
                      ('wProcessorLevel',W.WORD),('wProcessorRevision',W.WORD)]
        system_info=SYSTEM_INFO(); system_info_error=None
        try:
            try: get_system_info=kernel.GetNativeSystemInfo
            except AttributeError: get_system_info=kernel.GetSystemInfo
            get_system_info.argtypes=[C.POINTER(SYSTEM_INFO)]
            get_system_info.restype=None
            get_system_info(C.byref(system_info))
            max_application_address=int(system_info.lpMaximumApplicationAddress or 0)
            if max_application_address < 0x10000:
                system_info_error='SYSTEM_INFO_UNAVAILABLE'
        except (AttributeError,OSError,TypeError,ValueError):
            max_application_address=0
            system_info_error='SYSTEM_INFO_UNAVAILABLE'
        scan_end=max_application_address+1 if not system_info_error else 0x10000

        def valid_dialog(obj, route):
            try:
                if obj<0x10000 or obj%8 or qword(obj)!=target_vtable:
                    return None
                widget=qword(obj+8)
                closed=read(obj+0x114,1)[0]
                size_name=qword(obj+0x128)
                name=read(obj+0x118, min(15, max(0, size_name))).split(b'\0',1)[0].decode('utf-8','replace') if size_name else ''
                if not widget or closed or size_name != 14 or name != 'DefaultConfirm':
                    return None
                return {'object':hex(obj),'name':name,'widget':hex(widget),'route':route,
                        'raw':read(obj,0x1b8).hex()}
            except (OSError,RuntimeError,ValueError):
                return None

        # The peace probe established this UI-global pointer as a useful root.
        # The game/server roots cover the startup UI before that global settles.
        roots=[(game,0,'game')]
        direct_matches=[]
        try:
            ui_global=qword(base+0x23494d0)
            if ui_global: roots.append((ui_global,0,'ui_global'))
        except OSError:
            pass
        try:
            server=qword(game+0x1e00)
            if server:
                roots.append((server,0,'server'))
                # R34F observed the live DefaultConfirm at this server UI
                # route. Validate each bounded link instead of searching the
                # address space while the startup UI is still loading.
                node=qword(server+0x78)
                route='server+0x78'
                for _ in range(3):
                    candidate=valid_dialog(node,route+'+0x0')
                    if candidate:
                        direct_matches.append(candidate)
                        break
                    node=qword(node)
                    route+='+0x0'
        except OSError:
            pass
        queue=list(roots); visited=set(); graph_matches=list(direct_matches); cursor=0
        graph_started=time.monotonic(); graph_deadline=graph_started+2.0
        while cursor<len(queue) and len(visited)<4096 and not graph_matches and time.monotonic()<graph_deadline:
            address,depth,route=queue[cursor]; cursor+=1
            if address in visited or not 0x10000<=address<scan_end or address%8:
                continue
            visited.add(address)
            try:
                blob=read(address,4096)
            except OSError:
                try: blob=read(address,1024)
                except OSError: continue
            for offset in range(0,len(blob)-7,8):
                value=int.from_bytes(blob[offset:offset+8],'little')
                if value==target_vtable:
                    candidate=valid_dialog(address+offset,route+f'+{offset:#x}')
                    if candidate:
                        graph_matches.append(candidate); break
                if depth<4 and 0x10000<=value<scan_end and value%8==0:
                    if not base<=value<base+0x4000000 and value not in visited and len(queue)<4096:
                        queue.append((value,depth+1,route+f'+{offset:#x}'))
            if graph_matches: break
        unique={item['object']:item for item in graph_matches}
        graph_seconds=time.monotonic()-graph_started
        try: scan_start=int(os.environ.get('EU4_DIALOG_SCAN_START','0x10000'),0)
        except ValueError: scan_start=0x10000
        scan_start=max(0x10000,scan_start)
        scan_start-=scan_start%0x1000
        # Preserve the metadata fields consumed by older read-only reports;
        # there is no private-heap enumeration or read loop in this probe.
        scanned=0; started=time.monotonic(); next_scan_address=scan_start
        address_exhausted=False; scan_error=None; scan_error_address=None
        heap_time_limit=0.0; heap_limit=0
        report={'pid':args.pid,'read_only':True,'player_slot':player_slot,
                'dialogs':list(unique.values()),'known_ui_graph_visited':len(visited),
                'known_ui_graph_matches':len(graph_matches),'scan_start_address':hex(scan_start),
                'next_scan_address':hex(next_scan_address),'scanned_bytes':scanned,
                'heap_seconds':round(time.monotonic()-started,3),
                'graph_seconds':round(graph_seconds,3),
                'graph_time_limit_seconds':2,
                'heap_limit_bytes':heap_limit,'heap_time_limit_seconds':heap_time_limit,
                'scan_complete':address_exhausted,
                'scan_end_address':hex(scan_end),'scan_error':scan_error,
                'scan_error_address':scan_error_address,
                'search_note':'Known UI roots and bounded object graph only; private-heap scan disabled.'}
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8'); print(json.dumps(report,indent=2)); return
'''
assert source.count("        slots = []") == 1
source = source.replace("        slots = []", body + "\n        slots = []")
exec(compile(source, str(source_path), "exec"),
     {"__name__": "__main__", "__file__": str(source_path)})
