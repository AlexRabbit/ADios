@ECHO OFF
echo %~n0%~x0 started from Directory: %~d0%~p0
%~d0
cd %~d0%~p0
IF NOT EXIST hosts GOTO nohostsFile
IF "%OS%"=="Windows_NT" GOTO hostsFile
IF EXIST %winbootdir%\hosts*.* ATTRIB +A -H -R -S %winbootdir%\hosts*.*>NUL
IF EXIST %winbootdir%\hosts.MVP DEL %winbootdir%\hosts.MVP>NUL
IF EXIST %winbootdir%\hosts REN %winbootdir%\hosts hosts.MVP>NUL
IF EXIST %winbootdir%\NUL COPY /Y hosts %winbootdir%>NUL
GOTO nohostsFile
:hostsFile
IF EXIST %windir%\SYSTEM32\DRIVERS\ETC\hosts*.* ATTRIB +A -H -R -S %windir%\SYSTEM32\DRIVERS\ETC\hosts*.*>NUL
IF EXIST %windir%\SYSTEM32\DRIVERS\ETC\hosts.MVP DEL %windir%\SYSTEM32\DRIVERS\ETC\hosts.MVP>NUL
IF EXIST %windir%\SYSTEM32\DRIVERS\ETC\hosts REN %windir%\SYSTEM32\DRIVERS\ETC\hosts hosts.MVP>NUL
IF EXIST %windir%\SYSTEM32\DRIVERS\ETC\NUL COPY /Y hosts %windir%\SYSTEM32\DRIVERS\ETC>NUL
	color 1F
	echo.
	echo.
	echo.
	echo. Previous version saved and renamed to hosts.MVP
:nohostsFile
Pause
EXIT