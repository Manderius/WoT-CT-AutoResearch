$ver = Get-Content .\version.txt
$modDir = ".\res\scripts\client\gui\mods\"
$modName = "mod_CTResearch"
$distFolder = ".\wotmod"

python2 -m py_compile .\mod_CTResearcher.py

mkdir "$modDir"
mv .\mod_CTResearcher.pyc (Join-Path -Path "$modDir" -ChildPath "${modName}_${ver}.pyc")
rm (Join-Path "$distFolder" ".\${modName}_${ver}.wotmod") -ErrorAction Ignore
Compress-Archive -Path .\res -CompressionLevel NoCompression -DestinationPath ".\${modName}_${ver}.zip"
mv ".\${modName}_${ver}.zip" (Join-Path "$distFolder" ".\${modName}_${ver}.wotmod")

rm -r .\res