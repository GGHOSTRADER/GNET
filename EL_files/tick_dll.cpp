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

#pragma comment(lib, "Ws2_32.lib")

// 🔴 IMPORTANT  🔴
// 1) SendTick is the function that EL defines — they must always match
// 2) _SendTick@40 = 40 bytes of parameters pushed onto the stack:
//    Lpstr(4) + int(4) + int(4) + double(8) + double(8) + int(4) + int(4) + int(4) = 40
#pragma comment(linker, "/EXPORT:SendTick=_SendTick@40")


static SOCKET g_sock = INVALID_SOCKET;
static bool   g_wsa_init = false;

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

static bool ensure_connected(const char* host, unsigned short port) {
    if (g_sock != INVALID_SOCKET) return true;

    if (!g_wsa_init) {
        WSADATA wsaData;
        if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) return false;
        g_wsa_init = true;
    }

    addrinfo hints{};
    hints.ai_family   = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    char port_str[16];
    std::snprintf(port_str, sizeof(port_str), "%u", port);

    addrinfo* result = nullptr;
    if (getaddrinfo(host, port_str, &hints, &result) != 0) return false;

    SOCKET s = socket(result->ai_family, result->ai_socktype, result->ai_protocol);
    if (s == INVALID_SOCKET) { freeaddrinfo(result); return false; }

    DWORD timeout_ms = 200;
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, (const char*)&timeout_ms, sizeof(timeout_ms));
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char*)&timeout_ms, sizeof(timeout_ms));

    int rc = connect(s, result->ai_addr, (int)result->ai_addrlen);
    freeaddrinfo(result);

    if (rc == SOCKET_ERROR) { closesocket(s); return false; }

    g_sock = s;
    return true;
}

static bool send_all(const char* data, int len) {
    if (g_sock == INVALID_SOCKET) return false;
    int sent_total = 0;
    while (sent_total < len) {
        int sent = send(g_sock, data + sent_total, len - sent_total, 0);
        if (sent == SOCKET_ERROR || sent == 0) { cleanup_socket(); return false; }
        sent_total += sent;
    }
    return true;
}

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
    if (!ensure_connected("127.0.0.1", 9010)) return 0;

    char buf[512];
    std::snprintf(
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

    return send_all(buf, (int)std::strlen(buf)) ? 1 : 0;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    if (ul_reason_for_call == DLL_PROCESS_DETACH) {
        cleanup_socket();
    }
    return TRUE;
}
