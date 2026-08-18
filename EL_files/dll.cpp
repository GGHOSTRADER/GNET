// BarBridge.cpp  (Win32/x86 DLL for TradeStation EasyLanguage)
//
// Exported function:
//   int __stdcall SendBar(const char* symbol, int yyyymmdd, int hhmmss,
//                         double o, double h, double l, double c, double Up,
//                         double down, double vwap, int bar);
//
// Behavior:
//   - Connects to 127.0.0.1:9009 (Python listener)
//   - Sends: symbol,yyyymmdd,hhmmss,open,high,low,close,Up,down,vwap,barnumber\n
//   - Returns 1 on success, 0 on failure
//
// Notes:
//   - Use Win32 Release build
//   - Keep this DLL "dumb": no heavy work, no long blocking calls


// ---------------------------------------------------------------
// Compile instructions:
//----------------------------------------------------------------
// GOT TO LAUNCH DEVELOPER FROM VSSTUDIO
// cd to the directory containing this file
// cl /LD /EHsc dll.cpp ws2_32.lib /Fe:BarBridge.dll
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
// 1) SendBar is the function that EL define, they must always match
// 2) _SendBar@xx is always changed when number of variables changes
//      Due to how many bytes are pushed onto the stack for parameters
#pragma comment(linker, "/EXPORT:SendBar=_SendBar@64")


static FailFastSocket g_client;
static SRWLOCK g_lock = SRWLOCK_INIT;

// Must have the right parameters here to send through Sendbar function
extern "C" __declspec(dllexport) int __stdcall SendBar(
    const char* symbol,
    int yyyymmdd,
    int hhmmss,
    double o,
    double h,
    double l,
    double c,
    int up,
    int down,
    double vwap,
    int bar
) {
    char buf[512];
    const int length = std::snprintf(
        buf, sizeof(buf),
        //%.10g is used for float and double
        // %d is used for intergers
        // %s for strings
        "%s,%d,%d,%.10g,%.10g,%.10g,%.10g,%d,%d,%.10g,%d\n",
        (symbol ? symbol : ""),
        yyyymmdd,
        hhmmss,
        o, h, l, c,
        up,
        down,
        vwap,
        bar
    );
    if (length <= 0 || length >= static_cast<int>(sizeof(buf))) return 0;
    if (!TryAcquireSRWLockExclusive(&g_lock)) return 0;
    const bool connected = g_client.ensure_connected("127.0.0.1", 9009);
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
