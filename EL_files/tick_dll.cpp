// TickBridge.cpp  (Win32/x86 DLL for TradeStation EasyLanguage)
//
// Exported function:
//   int __stdcall SendTick(const char* symbol, int yyyymmdd, int hhmmss,
//                          double high, double low, int up, int down, int bar_num);
//
// Behavior:
//   - Connects to 127.0.0.1:9010 (Python tick listener)
//   - Sends: symbol,yyyymmdd,hhmmss,high,low,up,down,bar_num\n
//   - Returns 1 on success, 0 on failure
//
// Notes:
//   - Use Win32 Release build
//   - Keep this DLL "dumb": no heavy work, no long blocking calls
//   - high == low for tick data (single price point)

//----------------------------------------------------------------
// Compile instructions:
//----------------------------------------------------------------
// Open "Developer Command Prompt for VS" from Windows Start menu
// cd to the directory containing this file
// cl /LD /EHsc tick_dll.cpp ws2_32.lib /Fe:TickBridge.dll
//----------------------------------------------------------------

#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <cstdio>
#include <string>

#include "fail_fast_socket.hpp"

#pragma comment(lib, "Ws2_32.lib")

// 🔴 IMPORTANT  🔴
// 1) SendTick is the function that EL defines — they must always match
// 2) _SendTick@40 = 40 bytes of parameters pushed onto the stack:
//    Lpstr(4) + int(4) + int(4) + double(8) + double(8) + int(4) + int(4) + int(4) = 40
#pragma comment(linker, "/EXPORT:SendTick=_SendTick@40")


static FailFastSocket g_client;
static SRWLOCK g_lock = SRWLOCK_INIT;

extern "C" __declspec(dllexport) int __stdcall SendTick(
    const char* symbol,
    int  yyyymmdd,
    int  hhmmss,
    double high,
    double low,
    int  up,
    int  down,
    int  bar_num
) {
    char buf[512];
    const int length = std::snprintf(
        buf, sizeof(buf),
        "%s,%d,%d,%.10g,%.10g,%d,%d,%d\n",
        (symbol ? symbol : ""),
        yyyymmdd,
        hhmmss,
        high,
        low,
        up,
        down,
        bar_num
    );
    if (length <= 0 || length >= static_cast<int>(sizeof(buf))) return 0;
    if (!TryAcquireSRWLockExclusive(&g_lock)) return 0;
    const bool connected = g_client.ensure_connected("127.0.0.1", 9010);
    const bool sent = connected && g_client.send_all(buf, length);
    ReleaseSRWLockExclusive(&g_lock);
    return sent ? 1 : 0;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    if (ul_reason_for_call == DLL_PROCESS_DETACH) {
        g_client.shutdown();
    }
    return TRUE;
}
