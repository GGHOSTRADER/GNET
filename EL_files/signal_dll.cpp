// SignalBridge.cpp  (Win32/x86 DLL for TradeStation EasyLanguage)
//
// Exported functions use an instance_id argument so multiple TradeStation
// windows can safely share one connection and receive only their own result:
//
//   int    __stdcall RecvDecision(instance_id);
//   int    __stdcall GetDecisionApproved(instance_id);
//   double __stdcall GetDecisionProb(instance_id);
//   char*  __stdcall GetDecisionStatus(instance_id);
//   char*  __stdcall GetDecisionCandidateId(instance_id);
//
// Behavior:
//   - Connects to 127.0.0.1:9011 (Python signal_tcp_server)
//   - Persistent connection: stays open between EL calls
//   - Non-blocking receive and one in-memory queue per strategy instance
//   - Returns 1 when that strategy has a decision, 0 when it does not, and -1
//     on a connection error
//   - The candidate ID lets EL reject stale or unrelated decisions
//
// Compile (from VS Developer Command Prompt):
//   cl /LD /EHsc signal_dll.cpp ws2_32.lib /Fe:SignalBridge.dll

#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <cstdio>
#include <cstring>
#include <deque>
#include <map>
#include <string>

#include "fail_fast_socket.hpp"

#pragma comment(lib, "Ws2_32.lib")

// On x86, extern "C" __stdcall exports decorated names, so aliases expose
// default -- alias it to the plain name EL's External: declaration expects.
// On x64 there is no stdcall decoration: __declspec(dllexport) extern "C"
// already exports the plain name, so no aliasing is needed (or possible --
// "_Name@0" doesn't exist as a symbol on x64).
#ifndef _WIN64
#pragma comment(linker, "/EXPORT:RecvDecision=_RecvDecision@4")
#pragma comment(linker, "/EXPORT:GetDecisionApproved=_GetDecisionApproved@4")
#pragma comment(linker, "/EXPORT:GetDecisionProb=_GetDecisionProb@4")
#pragma comment(linker, "/EXPORT:GetDecisionStatus=_GetDecisionStatus@4")
#pragma comment(linker, "/EXPORT:GetDecisionCandidateId=_GetDecisionCandidateId@4")
#endif

static FailFastSocket g_client;
static char   g_buf[8192];
static int    g_buf_len  = 0;
static SRWLOCK g_lock = SRWLOCK_INIT;

struct Decision {
    std::string candidate_id;
    std::string status;
    int approved;
    double probability;
};

static std::map<std::string, std::deque<Decision>> g_queued;
static std::map<std::string, Decision> g_last;

static void disconnect_socket() {
    g_client.disconnect_with_backoff();
    g_buf_len = 0;
}

extern "C" __declspec(dllexport) int __stdcall RecvDecision(const char* instance_id) {
    if (!instance_id) return -2;
    if (!TryAcquireSRWLockExclusive(&g_lock)) return 0;
    if (!g_client.ensure_connected("127.0.0.1", 9011)) {
        ReleaseSRWLockExclusive(&g_lock);
        return -1;
    }

    // Drain available bytes into internal buffer
    char tmp[256];
    int n = g_client.receive(tmp, sizeof(tmp) - 1);
    if (n > 0) {
        if (g_buf_len + n < (int)sizeof(g_buf)) {
            memcpy(g_buf + g_buf_len, tmp, n);
            g_buf_len += n;
        }
    } else if (n == 0) {
        // Server closed the connection
        disconnect_socket();
        ReleaseSRWLockExclusive(&g_lock);
        return -1;
    } else {
        int err = WSAGetLastError();
        if (err != WSAEWOULDBLOCK && err != WSAETIMEDOUT) {
            disconnect_socket();
            ReleaseSRWLockExclusive(&g_lock);
            return -1;
        }
        // WSAEWOULDBLOCK / WSAETIMEDOUT = no data ready, that's fine
    }

    // Drain every complete correlated decision into its strategy queue.
    char* newline = nullptr;
    while ((newline = (char*)memchr(g_buf, '\n', g_buf_len)) != nullptr) {
        *newline = '\0';
        std::string line(g_buf);
        int line_len = (int)(newline - g_buf) + 1;
        g_buf_len -= line_len;
        memmove(g_buf, newline + 1, g_buf_len);

        char strategy[65] = {}, instance[65] = {}, candidate[65] = {}, symbol[65] = {};
        char status[65] = {};
        int date = 0, time_s = 0, bar_num = 0, direction = 0, approved = 0;
        double probability = 0.0;
        int parsed = sscanf(
            line.c_str(),
            "%64[^,],%64[^,],%64[^,],%64[^,],%d,%d,%d,%d,%64[^,],%d,%lf",
            strategy, instance, candidate, symbol, &date, &time_s, &bar_num, &direction,
            status, &approved, &probability
        );
        if (parsed == 11) {
            g_queued[instance].push_back(
                Decision{candidate, status, approved, probability}
            );
        }
    }

    std::deque<Decision>& queue = g_queued[instance_id];
    if (queue.empty()) {
        ReleaseSRWLockExclusive(&g_lock);
        return 0;
    }
    g_last[instance_id] = queue.front();
    queue.pop_front();
    ReleaseSRWLockExclusive(&g_lock);
    return 1;
}

extern "C" __declspec(dllexport) int __stdcall GetDecisionApproved(const char* instance_id) {
    if (!TryAcquireSRWLockShared(&g_lock)) return 0;
    int value = instance_id && g_last.count(instance_id) ? g_last[instance_id].approved : 0;
    ReleaseSRWLockShared(&g_lock);
    return value;
}

extern "C" __declspec(dllexport) double __stdcall GetDecisionProb(const char* instance_id) {
    if (!TryAcquireSRWLockShared(&g_lock)) return 0.0;
    double value = instance_id && g_last.count(instance_id)
        ? g_last[instance_id].probability : 0.0;
    ReleaseSRWLockShared(&g_lock);
    return value;
}

extern "C" __declspec(dllexport) char* __stdcall GetDecisionStatus(const char* instance_id) {
    static thread_local char value[65];
    value[0] = '\0';
    if (!TryAcquireSRWLockShared(&g_lock)) return value;
    if (instance_id && g_last.count(instance_id))
        strncpy_s(value, g_last[instance_id].status.c_str(), _TRUNCATE);
    ReleaseSRWLockShared(&g_lock);
    return value;
}

extern "C" __declspec(dllexport) char* __stdcall GetDecisionCandidateId(const char* instance_id) {
    static thread_local char value[65];
    value[0] = '\0';
    if (!TryAcquireSRWLockShared(&g_lock)) return value;
    if (instance_id && g_last.count(instance_id))
        strncpy_s(value, g_last[instance_id].candidate_id.c_str(), _TRUNCATE);
    ReleaseSRWLockShared(&g_lock);
    return value;
}

BOOL APIENTRY DllMain(HMODULE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_DETACH) g_client.shutdown();
    return TRUE;
}
