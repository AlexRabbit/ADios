@ECHO OFF
echo %~n0%~x0 started from Directory: %~d0%~p0
%~d0
cd %~d0%~p0
echo %DATE%
echo %TIME%


IF NOT EXIST HOSTS GOTO noHostsFile
IF "%OS%"=="Windows_NT" GOTO HostsFile
IF EXIST %winbootdir%\HOSTS*.* ATTRIB +A -H -R -S %winbootdir%\HOSTS*.*>NUL
IF EXIST %winbootdir%\HOSTS.MVP DEL %winbootdir%\HOSTS.MVP>NUL
IF EXIST %winbootdir%\HOSTS REN %winbootdir%\HOSTS HOSTS.MVP>NUL
IF EXIST %winbootdir%\NUL COPY /Y HOSTS %winbootdir%>NUL
GOTO noHostsFile
:HostsFile
IF EXIST %windir%\SYSTEM32\DRIVERS\ETC\HOSTS*.* ATTRIB +A -H -R -S %windir%\SYSTEM32\DRIVERS\ETC\HOSTS*.*>NUL
IF EXIST %windir%\SYSTEM32\DRIVERS\ETC\HOSTS.MVP DEL %windir%\SYSTEM32\DRIVERS\ETC\HOSTS.MVP>NUL
IF EXIST %windir%\SYSTEM32\DRIVERS\ETC\HOSTS REN %windir%\SYSTEM32\DRIVERS\ETC\HOSTS HOSTS.MVP>NUL
IF EXIST %windir%\SYSTEM32\DRIVERS\ETC\NUL COPY /Y HOSTS %windir%\SYSTEM32\DRIVERS\ETC>NUL
	color 1F
	echo.
	echo  AlexRabbit/TheUltimateADblocker
	echo  https://github.com/AlexRabbit/TheUltimateADblocker 
	echo  
	echo  NOW YOU HAVE 0 ADS, CONGRATULATIONS
:noHostsFile
Pause
Windows Registry Editor Version 5.00
[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\Psched]
"NonBestEffortLimit"=dword:00000000
sc config wuauserv start= auto
sc config bits start= auto
sc config DcomLaunch start= 
net start bits
net start DcomLaunch
reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update" /v AUOptions /t REG_DWORD /d 1 /f
reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update" /v AUOptions /t REG_DWORD /d 0 /f
sc config wuauserv start= auto
sc config wuauserv start= 
netsh int ip reset resetlog.txt
netsh int ip reset resetlog.txt
netsh int ip reset 
netsh int ip reset c:\Reset.
netsh int ipv4 reset 
netsh advfirewall firewall add rule name=”YoutubeBufferTrick” dir=in action=block remoteip=173.194.55.0/24,206.111.0.0/16 enable=yes
ipconfig
ipconfig /release
ipconfig /renew
ipconfig /flushdns
netsh int tcp show global 
netsh int tcp set global chimney=enabled
netsh int tcp set global autotuninglevel=normal 
netsh int tcp set global congestionprovider=ctcp 
NETSH INT IP RESET C:\RESETLOG.txt
netsh winsock reset
EXIT