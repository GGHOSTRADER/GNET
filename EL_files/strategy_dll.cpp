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

#pragma comment(lib, "Ws2_32.lib")
#pragma comment(lib, "Ole32.lib")

#ifndef _WIN64
#pragma comment(linker, "/EXPORT:SendCandidate=_SendCandidate@28")
#pragma comment(linker, "/EXPORT:GetLastCandidateId=_GetLastCandidateId@4")
#endif

static SOCKET g_sock = INVALID_SOCKET;
static bool g_wsa_init = false;
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

static void cleanup_socket() {
    if (g_sock != INVALID_SOCKET) {
        closesocket(g_sock);
        g_sock = INVALID_SOCKET;
    }
    if (g_wsa_init) {
        WSACleanup();
        g_wsa_init = false;
    }
}

static bool ensure_connected() {
    if (g_sock != INVALID_SOCKET) return true;
    if (!g_wsa_init) {
        WSADATA data;
        if (WSAStartup(MAKEWORD(2, 2), &data) != 0) return false;
        g_wsa_init = true;
    }
    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;
    addrinfo* result = nullptr;
    if (getaddrinfo("127.0.0.1", "9012", &hints, &result) != 0) return false;
    SOCKET candidate = socket(
        result->ai_family, result->ai_socktype, result->ai_protocol
    );
    if (candidate == INVALID_SOCKET) {
        freeaddrinfo(result);
        return false;
    }
    if (connect(candidate, result->ai_addr, (int)result->ai_addrlen) == SOCKET_ERROR) {
        closesocket(candidate);
        freeaddrinfo(result);
        return false;
    }
    freeaddrinfo(result);
    g_sock = candidate;
    return true;
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
    AcquireSRWLockExclusive(&g_lock);
    int result = -1;
    char candidate_id[37] = {};
    if (create_candidate_id(candidate_id, sizeof(candidate_id)) && ensure_connected()) {
        char line[512];
        int length = _snprintf_s(
            line, sizeof(line), _TRUNCATE, "%s,%s,%s,%s,%d,%d,%d,%d\n",
            strategy_id, instance_id, candidate_id, symbol,
            date, time_s, bar_num, direction
        );
        if (length > 0) {
            int sent = 0;
            while (sent < length) {
                int count = send(g_sock, line + sent, length - sent, 0);
                if (count == SOCKET_ERROR || count == 0) {
                    cleanup_socket();
                    break;
                }
                sent += count;
            }
            if (sent == length) {
                g_last_candidate_by_instance[instance_id] = candidate_id;
                result = 1;
            }
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
    AcquireSRWLockShared(&g_lock);
    std::map<std::string, std::string>::const_iterator found =
        g_last_candidate_by_instance.find(instance_id);
    if (found != g_last_candidate_by_instance.end()) {
        strncpy_s(value, sizeof(value), found->second.c_str(), _TRUNCATE);
    }
    ReleaseSRWLockShared(&g_lock);
    return value;
}

BOOL APIENTRY DllMain(HMODULE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_DETACH) cleanup_socket();
    return TRUE;
}
