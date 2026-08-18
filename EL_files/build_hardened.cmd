@echo off
setlocal

set "VCVARS=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars32.bat"
set "OUTPUT=%~dp0build_hardened"

if not exist "%VCVARS%" (
    echo x86 Visual Studio environment was not found at "%VCVARS%".
    exit /b 1
)

if not exist "%OUTPUT%" mkdir "%OUTPUT%"
call "%VCVARS%" || exit /b 1

cl /nologo /LD /EHsc "%~dp0dll.cpp" ws2_32.lib ^
    /Fo:"%OUTPUT%\dll.obj" /Fe:"%OUTPUT%\BarBridge.dll" || exit /b 1
cl /nologo /LD /EHsc "%~dp0tick_dll.cpp" ws2_32.lib ^
    /Fo:"%OUTPUT%\tick_dll.obj" /Fe:"%OUTPUT%\TickBridge.dll" || exit /b 1
cl /nologo /LD /EHsc "%~dp0signal_dll.cpp" ws2_32.lib ^
    /Fo:"%OUTPUT%\signal_dll.obj" /Fe:"%OUTPUT%\SignalBridge.dll" || exit /b 1
cl /nologo /LD /EHsc "%~dp0strategy_dll.cpp" ws2_32.lib ole32.lib ^
    /Fo:"%OUTPUT%\strategy_dll.obj" /Fe:"%OUTPUT%\StrategyBridge.dll" || exit /b 1

echo Hardened x86 DLLs built in "%OUTPUT%".
