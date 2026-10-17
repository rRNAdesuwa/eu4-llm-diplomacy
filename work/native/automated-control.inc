// Test-save control, evaluated exclusively on the observed game frame thread.
static wchar_t control_request[MAX_PATH];
static int32_t control_target=0;
static ULONGLONG control_deadline=0;
static bool control_pause_after_load=false;
static unsigned control_load_wait_frames=0;
static bool control_ready() {
    uintptr_t game=0,server=0,vtable=0,get_pause=0;
    if (!read(base+0x233fe58,game) || !read(game+0x1e00,server)
        || !read(server,vtable) || !read(vtable+0x100,get_pause)
        || get_pause<base+0x1000 || get_pause>=base+0x1c00000) return false;
    // This is the same accessor used by gamespeed before IsPaused.
    // During load it can return null even after POR's world has appeared.
    uintptr_t pause=reinterpret_cast<uintptr_t (*)(void*)>(get_pause)(reinterpret_cast<void*>(server));
    unsigned char paused=0;
    return read(pause+0x48,paused) && pause>=0x10000;
}
static bool automated_control_start(const wchar_t* directory) {
    if (swprintf(control_request,MAX_PATH,L"%ls\\game-control.request",directory)<0) return false;
    return GetFileAttributesW(control_request)==INVALID_FILE_ATTRIBUTES || DeleteFileW(control_request);
}
static bool control_call(int save,const char* argument) {
    if (!control_ready()) return false;
    uintptr_t entry=0;
    uintptr_t slot=save==2?0x1fc7558:save?0x1fc74b8:0x1fce998;
    uintptr_t function=save==2?0xe7ac80:save?0xe7b250:0xe91210;
    if (!read(base+slot,entry) || entry!=base+function) return false;
    NativeShortString value{}; value.capacity=15;
    NativeStringVector args{};
    if (argument) {
        value.text[0]=argument[0]; value.size=1;
        args={&value,&value+1,&value+1};
    }
    NativeConsoleResult result{};
    using Evaluate=void* (*)(void*,const void*);
    reinterpret_cast<Evaluate>(entry)(&result,&args);
    bool success=result.success!=0;
    reinterpret_cast<void (*)(void*)>(base+0x95660)(&result.message);
    char message[200];
    snprintf(message,sizeof(message),"{\"event\":\"control_console_result\",\"command\":\"%s\",\"success\":%s,\"thread\":%lu}\n",
        save==2?"autosave":save?"savegame":argument,success?"true":"false",static_cast<unsigned long>(GetCurrentThreadId()));
    line(message); return success;
}
static void automated_control_tick() {
    uintptr_t game=0; uint64_t player=0; int32_t date=0;
    if (!read(base+0x233fe58,game) || !read(game+0x1e60,player)
        || (player&0xffffff)!=0x524f50 || ((player>>32)&0xffff)!=189
        || !read(game+0x1dd0,date)) return;
    if (control_load_wait_frames) { --control_load_wait_frames; return; }
    if (!control_ready()) return;
    if (control_pause_after_load) {
        control_pause_after_load=false; control_call(0,"0");
        line("{\"event\":\"control_loaded_pause_requested\"}\n");
    }
    if (control_target && (date>=control_target || GetTickCount64()>=control_deadline)) {
        bool paused=control_call(false,"0");
        char message[220];
        snprintf(message,sizeof(message),"{\"event\":\"control_advance_complete\",\"date_raw\":%d,\"target_raw\":%d,\"reached\":%s,\"paused_command_success\":%s}\n",
            date,control_target,date>=control_target?"true":"false",paused?"true":"false");
        line(message); control_target=0;
    }
    if (GetFileAttributesW(control_request)==INVALID_FILE_ATTRIBUTES) return;
    char request[64]{};
    HANDLE file=CreateFileW(control_request,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return;
    DWORD size=GetFileSize(file,nullptr),got=0;
    bool valid=size<sizeof(request) && ReadFile(file,request,size,&got,nullptr) && got==size;
    CloseHandle(file);
    if (!DeleteFileW(control_request) || !valid) return;
    if (strcmp(request,"TEST_ONLY savegame\n")==0) {
        if (!control_target) control_call(true,nullptr);
        return;
    }
    if (strcmp(request,"TEST_ONLY autosave\n")==0) {
        if (!control_target) control_call(2,nullptr);
        return;
    }
    if (strcmp(request,"TEST_ONLY pause\n")==0) {
        control_call(false,"0"); control_target=0; return;
    }
    if (strcmp(request,"TEST_ONLY advance_35_days\n")==0
        || strcmp(request,"TEST_ONLY advance_5_days\n")==0
        || strcmp(request,"TEST_ONLY advance_1_days\n")==0) {
        if (control_target) return;
        const int days=strcmp(request,"TEST_ONLY advance_1_days\n")==0?1:
            strcmp(request,"TEST_ONLY advance_5_days\n")==0?5:35;
        control_target=date+days*24; control_deadline=GetTickCount64()+120000;
        if (!control_call(false,"4")) control_target=0;
        char message[80];
        snprintf(message,sizeof(message),"{\"event\":\"control_advance_begin\",\"days\":%d}\n",days);
        line(message);
    }
}
