// SignalBridge.cpp  (Win32/x86 DLL for TradeStation EasyLanguage)
//
// Exported functions (all __stdcall, zero parameters, plain value returns --
// no by-reference / pointer-output parameters, since EasyLanguage's
// External: declaration does not support "int ref" / "double ref" style
// out-params -- see RecvSignal's old signature in git history, which
// crashed TS with "invalid number of parameters passed"):
//
//   int    __stdcall RecvSignal();  -- poll socket, parse + cache one line
//   int    __stdcall GetSignal();   -- cached: 1 = buy, 0 = no trade
//   double __stdcall GetProb();     -- cached sigmoid probability
//   char*  __stdcall GetSymbol();   -- cached symbol string (Lpstr)
//
// Behavior:
//   - Connects to 127.0.0.1:9011 (Python signal_tcp_server)
//   - Persistent connection: stays open between EL calls
//   - Non-blocking recv: RecvSignal() returns 0 immediately if no signal ready
//   - On a complete line: parses "symbol,signal,prob" and caches all three
//   - RecvSignal() returns:  1 = new signal parsed (call Get* to read it)
//                             0 = no data ready yet (cached values unchanged)
//                            -1 = connection error (will reconnect on next call)
//
// EasyLanguage usage:
//   vars: sig_symbol(""), sig_int(0), sig_prob(0.0), ok(0);
//   ok = RecvSignal();
//   If ok = 1 Then Begin
//       sig_int    = GetSignal();
//       sig_prob   = GetProb();
//       sig_symbol = GetSymbol();
//       If sig_int = 1 Then Buy next bar at market;
//   End;
//
// Compile (from VS Developer Command Prompt):
//   cl /LD /EHsc signal_dll.cpp ws2_32.lib /Fe:SignalBridge.dll

#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <cstdio>
#include <cstring>
#include <string>

#pragma comment(lib, "Ws2_32.lib")

// On x86, extern "C" __stdcall with zero params is exported as "_Name@0" by
// default -- alias it to the plain name EL's External: declaration expects.
// On x64 there is no stdcall decoration: __declspec(dllexport) extern "C"
// already exports the plain name, so no aliasing is needed (or possible --
// "_Name@0" doesn't exist as a symbol on x64).
#ifndef _WIN64
#pragma comment(linker, "/EXPORT:RecvSignal=_RecvSignal@0")
#pragma comment(linker, "/EXPORT:GetSignal=_GetSignal@0")
#pragma comment(linker, "/EXPORT:GetProb=_GetProb@0")
#pragma comment(linker, "/EXPORT:GetSymbol=_GetSymbol@0")
#endif

static SOCKET g_sock     = INVALID_SOCKET;
static bool   g_wsa_init = false;
static char   g_buf[1024];
static int    g_buf_len  = 0;

// Cached values from the most recently parsed "symbol,signal,prob" line
static char   g_symbol[64] = {};
static int    g_signal     = 0;
static double g_prob       = 0.0;

static void cleanup_socket() {
    if (g_sock != INVALID_SOCKET) {
        closesocket(g_sock);
        g_sock = INVALID_SOCKET;
    }
    if (g_wsa_init) {
        WSACleanup();
        g_wsa_init = false;
    }
    g_buf_len = 0;
}

static bool ensure_connected() {
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

    addrinfo* result = nullptr;
    if (getaddrinfo("127.0.0.1", "9011", &hints, &result) != 0) return false;

    SOCKET s = socket(result->ai_family, result->ai_socktype, result->ai_protocol);
    if (s == INVALID_SOCKET) { freeaddrinfo(result); return false; }

    // 200 ms send/recv timeout so EL never blocks
    DWORD timeout_ms = 200;
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, (const char*)&timeout_ms, sizeof(timeout_ms));
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char*)&timeout_ms, sizeof(timeout_ms));

    if (connect(s, result->ai_addr, (int)result->ai_addrlen) == SOCKET_ERROR) {
        closesocket(s);
        freeaddrinfo(result);
        return false;
    }

    freeaddrinfo(result);

    // Switch to non-blocking after connect
    u_long mode = 1;
    ioctlsocket(s, FIONBIO, &mode);

    g_sock = s;
    return true;
}

extern "C" __declspec(dllexport) int __stdcall RecvSignal() {
    if (!ensure_connected()) return -1;

    // Drain available bytes into internal buffer
    char tmp[256];
    int n = recv(g_sock, tmp, sizeof(tmp) - 1, 0);
    if (n > 0) {
        if (g_buf_len + n < (int)sizeof(g_buf)) {
            memcpy(g_buf + g_buf_len, tmp, n);
            g_buf_len += n;
        }
    } else if (n == 0) {
        // Server closed the connection
        cleanup_socket();
        return -1;
    } else {
        int err = WSAGetLastError();
        if (err != WSAEWOULDBLOCK && err != WSAETIMEDOUT) {
            cleanup_socket();
            return -1;
        }
        // WSAEWOULDBLOCK / WSAETIMEDOUT = no data ready, that's fine
    }

    // Look for a complete line in g_buf
    char* newline = (char*)memchr(g_buf, '\n', g_buf_len);
    if (!newline) return 0;  // no full line yet

    *newline = '\0';
    std::string line(g_buf);

    // Shift remaining bytes to front
    int line_len = (int)(newline - g_buf) + 1;
    g_buf_len -= line_len;
    memmove(g_buf, newline + 1, g_buf_len);

    // Parse: symbol,signal,prob
    char sym[64]  = {};
    int  sig      = 0;
    double prob   = 0.0;

    // sscanf with %63[^,] reads up to 63 chars that are not ','
    if (sscanf(line.c_str(), "%63[^,],%d,%lf", sym, &sig, &prob) != 3) {
        return 0;  // malformed line -- skip, wait for next
    }

    strncpy(g_symbol, sym, 63);
    g_symbol[63] = '\0';
    g_signal = sig;
    g_prob   = prob;
    return 1;
}

extern "C" __declspec(dllexport) int __stdcall GetSignal() {
    return g_signal;
}

extern "C" __declspec(dllexport) double __stdcall GetProb() {
    return g_prob;
}

extern "C" __declspec(dllexport) char* __stdcall GetSymbol() {
    return g_symbol;
}

BOOL APIENTRY DllMain(HMODULE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_DETACH) cleanup_socket();
    return TRUE;
}
