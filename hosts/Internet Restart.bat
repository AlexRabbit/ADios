
Windows Registry Editor Version 5.00
[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\Psched]
"NonBestEffortLimit"=dword:00000000
sc config wuauserv start= auto
sc config bits start= auto
sc config DcomLaunch start= auto
net stop bits
net start bits
net start DcomLaunch
reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update" /v AUOptions /t REG_DWORD /d 1 /f
reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update" /v AUOptions /t REG_DWORD /d 0 /f
netsh int ip reset 
netsh int ip reset c:\Reset.
netsh int ipv4 reset 
ipconfig
ipconfig /release
ipconfig /renew
ipconfig /flushdns
netsh int tcp show global 
netsh winsock reset
