#pragma once

#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <cstdio>

// A small, caller-synchronized TCP client for code running inside TradeStation.
// Connection attempts are capped at 2 ms and throttled after failure. Established
// sockets stay non-blocking, so Python downtime never blocks a chart thread.
class FailFastSocket {
public:
    static const DWORD RETRY_BACKOFF_MS = 2000;
    static const long CONNECT_WAIT_US = 2000;

    FailFastSocket()
        : socket_(INVALID_SOCKET), wsa_started_(false), next_retry_ms_(0) {}

    bool ensure_connected(const char* host, unsigned short port) {
        if (socket_ != INVALID_SOCKET) return true;

        const ULONGLONG now = GetTickCount64();
        if (now < next_retry_ms_) return false;
        next_retry_ms_ = now + RETRY_BACKOFF_MS;

        if (!wsa_started_) {
            WSADATA data;
            if (WSAStartup(MAKEWORD(2, 2), &data) != 0) return false;
            wsa_started_ = true;
        }

        addrinfo hints{};
        hints.ai_family = AF_INET;
        hints.ai_socktype = SOCK_STREAM;
        hints.ai_protocol = IPPROTO_TCP;

        char port_text[16];
        std::snprintf(port_text, sizeof(port_text), "%u", port);
        addrinfo* addresses = nullptr;
        if (getaddrinfo(host, port_text, &hints, &addresses) != 0) return false;

        SOCKET candidate = socket(
            addresses->ai_family,
            addresses->ai_socktype,
            addresses->ai_protocol
        );
        if (candidate == INVALID_SOCKET) {
            freeaddrinfo(addresses);
            return false;
        }

        u_long non_blocking = 1;
        if (ioctlsocket(candidate, FIONBIO, &non_blocking) == SOCKET_ERROR) {
            closesocket(candidate);
            freeaddrinfo(addresses);
            return false;
        }

        int result = connect(
            candidate,
            addresses->ai_addr,
            static_cast<int>(addresses->ai_addrlen)
        );
        freeaddrinfo(addresses);

        if (result == SOCKET_ERROR) {
            const int error = WSAGetLastError();
            if (error != WSAEWOULDBLOCK && error != WSAEINPROGRESS &&
                error != WSAEINVAL) {
                closesocket(candidate);
                return false;
            }

            fd_set writable;
            FD_ZERO(&writable);
            FD_SET(candidate, &writable);
            timeval timeout{};
            timeout.tv_usec = CONNECT_WAIT_US;
            result = select(0, nullptr, &writable, nullptr, &timeout);
            if (result <= 0 || !FD_ISSET(candidate, &writable)) {
                closesocket(candidate);
                return false;
            }

            int socket_error = 0;
            int option_length = sizeof(socket_error);
            if (getsockopt(
                    candidate,
                    SOL_SOCKET,
                    SO_ERROR,
                    reinterpret_cast<char*>(&socket_error),
                    &option_length
                ) == SOCKET_ERROR || socket_error != 0) {
                closesocket(candidate);
                return false;
            }
        }

        socket_ = candidate;
        next_retry_ms_ = 0;
        return true;
    }

    bool send_all(const char* data, int length) {
        if (socket_ == INVALID_SOCKET) return false;
        int sent = 0;
        while (sent < length) {
            const int count = send(socket_, data + sent, length - sent, 0);
            if (count <= 0) {
                disconnect_with_backoff();
                return false;
            }
            sent += count;
        }
        return true;
    }

    int receive(char* output, int capacity) {
        if (socket_ == INVALID_SOCKET) return SOCKET_ERROR;
        return recv(socket_, output, capacity, 0);
    }

    void disconnect_with_backoff() {
        close_socket();
        next_retry_ms_ = GetTickCount64() + RETRY_BACKOFF_MS;
    }

    void shutdown() {
        close_socket();
        if (wsa_started_) {
            WSACleanup();
            wsa_started_ = false;
        }
        next_retry_ms_ = 0;
    }

private:
    void close_socket() {
        if (socket_ != INVALID_SOCKET) {
            closesocket(socket_);
            socket_ = INVALID_SOCKET;
        }
    }

    SOCKET socket_;
    bool wsa_started_;
    ULONGLONG next_retry_ms_;
};
