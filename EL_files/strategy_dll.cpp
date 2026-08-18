// StrategyBridge.cpp -- shared candidate sender for all TradeStation windows.
//
// Protocol:
//   strategy_id,instance_id,candidate_id,symbol,date,time_s,bar_num,direction\n
//
// Compile from the x86 Visual Studio Developer Command Prompt:
//   cl /LD /EHsc strategy_dll.cpp ws2_32.lib ole32.lib /Fe:StrategyBridge.dll

#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <objbase.h>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>

#include "fail_fast_socket.hpp"

#pragma comment(lib, "Ws2_32.lib")
#pragma comment(lib, "Ole32.lib")

#ifndef _WIN64
#pragma comment(linker, "/EXPORT:SendCandidate=_SendCandidate@28")
#pragma comment(linker, "/EXPORT:GetLastCandidateId=_GetLastCandidateId@4")
#endif

static FailFastSocket g_client;
static SRWLOCK g_lock = SRWLOCK_INIT;
static std::map<std::string, std::string> g_last_candidate_by_instance;

static bool create_candidate_id(char* output, size_t output_size) {
    GUID value;
    if (CoCreateGuid(&value) != S_OK) return false;
    int count = sprintf_s(
        output, output_size,
        "%08lX-%04X-%04X-%02X%02X-%02X%02X%02X%02X%02X%02X",
        value.Data1, value.Data2, value.Data3,
        value.Data4[0], value.Data4[1], value.Data4[2], value.Data4[3],
        value.Data4[4], value.Data4[5], value.Data4[6], value.Data4[7]
    );
    return count > 0;
}

extern "C" __declspec(dllexport) int __stdcall SendCandidate(
    const char* strategy_id,
    const char* instance_id,
    const char* symbol,
    int date,
    int time_s,
    int bar_num,
    int direction
) {
    if (!strategy_id || !instance_id || !symbol) return -2;
    if (!TryAcquireSRWLockExclusive(&g_lock)) return -1;
    int result = -1;
    char candidate_id[37] = {};
    if (create_candidate_id(candidate_id, sizeof(candidate_id)) &&
        g_client.ensure_connected("127.0.0.1", 9012)) {
        char line[512];
        int length = _snprintf_s(
            line, sizeof(line), _TRUNCATE, "%s,%s,%s,%s,%d,%d,%d,%d\n",
            strategy_id, instance_id, candidate_id, symbol,
            date, time_s, bar_num, direction
        );
        if (length > 0 && g_client.send_all(line, length)) {
            g_last_candidate_by_instance[instance_id] = candidate_id;
            result = 1;
        }
    }
    ReleaseSRWLockExclusive(&g_lock);
    return result;
}

extern "C" __declspec(dllexport) char* __stdcall GetLastCandidateId(
    const char* instance_id
) {
    static thread_local char value[37];
    value[0] = '\0';
    if (!instance_id) return value;
    if (!TryAcquireSRWLockShared(&g_lock)) return value;
    std::map<std::string, std::string>::const_iterator found =
        g_last_candidate_by_instance.find(instance_id);
    if (found != g_last_candidate_by_instance.end()) {
        strncpy_s(value, sizeof(value), found->second.c_str(), _TRUNCATE);
    }
    ReleaseSRWLockShared(&g_lock);
    return value;
}

BOOL APIENTRY DllMain(HMODULE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_DETACH) g_client.shutdown();
    return TRUE;
}
