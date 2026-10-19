@contextmanager
def _hold_new_phase_intent(path, raw):
    """Own one newly created intent until publication; never reopen an old one.

    Windows sharing permits readers (including read_evidence), but no other
    writer or delete/rename handle. A failed invocation permanently leaves the
    file behind. This is a private publisher helper, not an override parameter.
    """
    require(os.name == "nt", "Held phase intent requires Windows file identity")
    path = Path(path)
    _no_links(path)
    require(type(raw) is bytes and 0 < len(raw) <= 4096, "Invalid bounded phase intent")
    kernel = C.WinDLL("kernel32", use_last_error=True)
    class FileInformation(C.Structure):
        _fields_ = [("attributes", W.DWORD), ("creation", W.FILETIME),
            ("access", W.FILETIME), ("write", W.FILETIME), ("volume", W.DWORD),
            ("size_high", W.DWORD), ("size_low", W.DWORD), ("links", W.DWORD),
            ("index_high", W.DWORD), ("index_low", W.DWORD)]
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    kernel.WriteFile.argtypes = [W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p]
    kernel.WriteFile.restype = W.BOOL
    kernel.ReadFile.argtypes = kernel.WriteFile.argtypes
    kernel.ReadFile.restype = W.BOOL
    kernel.FlushFileBuffers.argtypes = [W.HANDLE]
    kernel.FlushFileBuffers.restype = W.BOOL
    kernel.SetFilePointerEx.argtypes = [W.HANDLE, C.c_longlong, C.POINTER(C.c_longlong), W.DWORD]
    kernel.SetFilePointerEx.restype = W.BOOL
    kernel.GetFileInformationByHandle.argtypes = [W.HANDLE, C.POINTER(FileInformation)]
    kernel.GetFileInformationByHandle.restype = W.BOOL
    invalid = C.c_void_p(-1).value
    # CREATE_NEW, GENERIC_READ|WRITE, FILE_SHARE_READ only. A preexisting file,
    # even byte-identical, can never become this invocation's owned intent.
    handle = kernel.CreateFileW(str(path), 0xc0000000, 1, None, 1, 0x80000080, None)
    if handle == invalid:
        raise OSError(C.get_last_error(), "Exclusive held phase intent creation failed")
    def file_identity(h):
        info = FileInformation()
        require(bool(kernel.GetFileInformationByHandle(h, C.byref(info))), "Cannot inspect held intent file identity")
        require(info.links == 1 and not info.attributes & (0x400 | 0x10), "Intent is linked, reparse, or directory")
        return (info.volume, info.index_high, info.index_low,
                info.creation.dwHighDateTime, info.creation.dwLowDateTime,
                info.size_high, info.size_low)
    try:
        written = W.DWORD()
        buffer = C.create_string_buffer(raw)
        require(bool(kernel.WriteFile(handle, buffer, len(raw), C.byref(written), None))
                and written.value == len(raw), "Short/failed held phase intent write")
        require(bool(kernel.FlushFileBuffers(handle)), "Phase intent flush failed")
        pinned = file_identity(handle)
        require(pinned[-2:] == (0, len(raw)), "Held intent size differs")
        def validate_owned():
            _no_links(path)
            require(file_identity(handle) == pinned, "Held intent identity changed")
            # OPEN_EXISTING reader must share this existing writer's access,
            # while the original handle still prohibits writes and deletion.
            current = kernel.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)
            if current == invalid:
                raise OSError(C.get_last_error(), "Cannot bind intent path to held file")
            try:
                require(file_identity(current) == pinned, "Intent path no longer names owned file")
            finally:
                kernel.CloseHandle(current)
            require(bool(kernel.SetFilePointerEx(handle, 0, None, 0)), "Cannot seek held intent")
            contents, count = C.create_string_buffer(len(raw) + 1), W.DWORD()
            require(bool(kernel.ReadFile(handle, contents, len(raw) + 1, C.byref(count), None))
                    and count.value == len(raw) and contents.raw[:count.value] == raw,
                    "Owned intent contents differ")
        validate_owned()
        yield validate_owned
    finally:
        kernel.CloseHandle(handle)


def _current_owned_phase_evidence(evidence, phase, validate_owned, final, claimed):
    """Internal, invocation-local projection; public readiness stays strict."""
    validate_owned()
    _no_links(final)
    _no_links(claimed)
    require(not final.exists() and not claimed.exists(), "Native request/claim appeared during phase publication")
    sources = evidence.get("phase_attempt_sources")
    require(type(sources) is dict and set(sources) == set(PHASES), "Missing exact phase attempt diagnostics")
    source = sources[phase]
    require(type(source) is dict and set(source) == {"native_started", "native_claim", "host_intent"}
            and source["native_started"] is False and source["native_claim"] is False and source["host_intent"] is True,
            "Phase attempt is not solely this invocation's held intent")
    require(type(evidence.get("phase_attempted")) is dict and set(evidence["phase_attempted"]) == set(PHASES)
            and evidence["phase_attempted"][phase] is True, "Owned phase intent was not observed by fresh evidence")
    return dict(evidence, phase_attempted=dict(evidence["phase_attempted"], **{phase: False}))


