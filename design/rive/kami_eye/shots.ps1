# Goz projesini dogrular ve 6 durumun ekran goruntusunu tek sayfada toplar (shots\_sheet.png)
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot
$r = "$env:USERPROFILE\.rive\bin\rive.exe"
cmd /c "$r . --verify 2>&1" | Select-Object -Last 2
cmd /c "$r inspect . --summary 2>&1" | Select-String 'severity'
New-Item -ItemType Directory -Force shots | Out-Null
$cases = [ordered]@{
  'a_center'   = '--advance=10'
  'b_right_err'= '--advance=10 --data=mouseX=1 --data=mouseY=1 --data=error=1'
  'c_left_fast'= '--advance=10 --data=mouseX=-1 --data=mouseY=-1 --data=downloadSpeed=1'
  'd_lidhalf'  = '--advance=10 --data=lid=0.5'
  'e_closed'   = '--advance=10 --data=lid=1'
  'f_blink'    = '--advance=229'
}
foreach ($k in $cases.Keys) { cmd /c "$r . --screenshot=shots\$k.png $($cases[$k]) 2>&1" | Select-String 'error|wrote' }
$py = "from PIL import Image; fs=['a_center','b_right_err','c_left_fast','d_lidhalf','e_closed','f_blink']; s=Image.new('RGB',(3*480,2*360),(40,30,60)); [s.paste(Image.open('shots/'+f+'.png').convert('RGB').crop((330,260,650,500)).resize((480,360)),((i%3)*480,(i//3)*360)) for i,f in enumerate(fs)]; s.save('shots/_sheet.png'); print('sheet ok')"
uv run --no-project --python 3.12 --with pillow python -c $py
