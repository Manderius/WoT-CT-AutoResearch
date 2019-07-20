$ver = Get-Content .\version.txt
$modDir = ".\res\scripts\client\gui\mods\"
$modName = "mod_CTResearcher"
$distFolder = ".\wotmod"
$7zip="C:\Program Files\7-zip\7z.exe"

python2 -m py_compile .\mod_CTResearcher.py

[xml]$xmlDoc = Get-Content .\meta.xml
$xmlDoc.root.version = "$ver"
$xmlDoc.Save(".\meta.xml")   

mkdir "$modDir"
mv .\mod_CTResearcher.pyc (Join-Path -Path "$modDir" -ChildPath "${modName}.pyc")
rm (Join-Path "$distFolder" "${modName}_*.wotmod") -ErrorAction Ignore
$params = "a", "-mx=0", (Join-Path "$distFolder" ".\${modName}_${ver}.zip"), ".\res", ".\meta.xml"
& $7zip $params
mv (Join-Path "$distFolder" "${modName}_${ver}.zip") (Join-Path "$distFolder" ".\${modName}_${ver}.wotmod")

rm -r .\res
