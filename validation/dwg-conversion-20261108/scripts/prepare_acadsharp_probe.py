from pathlib import Path
import urllib.request,json,hashlib,zipfile,subprocess,os
root=Path('C:/Users/18483/AppData/Local/Temp/vra-acadsharp-probe-20261108')
root.mkdir(exist_ok=False)
index=json.load(urllib.request.urlopen('https://api.nuget.org/v3-flatcontainer/acadsharp/index.json',timeout=40))
version=next(v for v in reversed(index['versions']) if '-' not in v)
url=f'https://api.nuget.org/v3-flatcontainer/acadsharp/{version}/acadsharp.{version}.nupkg'
data=urllib.request.urlopen(url,timeout=60).read();(root/'acadsharp.nupkg').write_bytes(data)
with zipfile.ZipFile(root/'acadsharp.nupkg') as z:
    (root/'package-files.json').write_text(json.dumps(z.namelist(),indent=2))
    (root/'ACadSharp.dll').write_bytes(z.read('lib/net8.0/ACadSharp.dll'))
    (root/'ACadSharp.xml').write_bytes(z.read('lib/net8.0/ACadSharp.xml'))
    (root/'ACadSharp.nuspec').write_bytes(z.read('ACadSharp.nuspec'))
(root/'download.json').write_text(json.dumps({'url':url,'version':version,'sha256':hashlib.sha256(data).hexdigest(),'verification':'TLS official NuGet download; local hash frozen, not independent publisher signature verification','source':'https://github.com/DomCR/ACadSharp','application_integrated':False},indent=2))
print(json.dumps({'version':version,'bytes':len(data),'root':str(root)}))
