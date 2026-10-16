# The PE export is parsed from the actual new DLL. No mapping, DllMain or callback.
def bridge_start_export_rva(path):
    import struct
    raw = read_bounded(Path(path), 32 * 1024 * 1024)
    def u16(o):
        require(0 <= o <= len(raw) - 2, "Truncated export PE")
        return struct.unpack_from("<H", raw, o)[0]
    def u32(o):
        require(0 <= o <= len(raw) - 4, "Truncated export PE")
        return struct.unpack_from("<I", raw, o)[0]
    require(raw[:2] == b"MZ", "Not a PE image")
    pe = u32(0x3c)
    require(pe <= 4096 and raw[pe:pe+4] == b"PE\0\0" and u16(pe+4) == 0x8664, "Expected AMD64 export PE")
    opt = pe + 24
    require(u16(opt) == 0x20b and u16(pe+20) >= 120 and u32(opt+108) >= 1,
            "Expected PE32+ optional header with an export directory")
    size_image = u32(opt+56)
    export, size_export = u32(opt+112), u32(opt+116)
    section_count, table = u16(pe+6), opt+u16(pe+20)
    require(1 <= section_count <= 96 and 0 < export < size_image and size_export >= 40,
            "Invalid bounded PE export directory")
    sections = []
    for index in range(section_count):
        h = table + 40*index
        sections.append((u32(h+12), u32(h+16), u32(h+20), u32(h+36)))
    def offset(rva, length):
        require(integer(rva,1,size_image-1) and integer(length,1,len(raw)), "Invalid bounded export RVA")
        for start,size,position,_ in sections:
            if start <= rva and rva + length <= start + size and position + rva-start + length <= len(raw):
                return position+rva-start
        raise LabError("Export RVA is outside backed sections")
    e = offset(export,40)
    functions,names = u32(e+20),u32(e+24)
    require(1 <= functions <= 4096 and 1 <= names <= 4096, "Export count bound")
    functions_at,names_at,ordinals_at = offset(u32(e+28),4*functions),offset(u32(e+32),4*names),offset(u32(e+36),2*names)
    matches=[]
    for index in range(names):
        name_at=offset(u32(names_at+4*index),1)
        end=raw.find(b"\0",name_at,min(len(raw),name_at+128))
        require(end != -1,"Unbounded export name")
        if raw[name_at:end] == b"BridgeStart":
            ordinal=u16(ordinals_at+2*index)
            require(ordinal < functions,"Export ordinal out of range")
            rva=u32(functions_at+4*ordinal)
            require(not export <= rva < export+size_export,"Forwarded BridgeStart is unsupported")
            offset(rva,1)
            require(any(start <= rva < start+size and flags & 0x20000000 for start,size,_,flags in sections),
                    "BridgeStart is not in an executable section")
            matches.append(rva)
    require(len(matches)==1,"Expected unique real BridgeStart export")
    return matches[0]
