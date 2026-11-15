from pathlib import Path
import subprocess,json,hashlib
root=Path('C:/Users/18483/AppData/Local/Temp/vra-acadsharp-probe-20261108')
source=r'''using System;
using System.Text;
using System.Text.Json;
using ACadSharp.IO;
public static class Converter {
  static string phase="read";
  static void Note(object sender,NotificationEventArgs e) {
    Console.WriteLine(JsonSerializer.Serialize<object>(new {phase=phase,type=e.NotificationType.ToString(),message=e.Message},(JsonSerializerOptions)null));
  }
  public static int Main(string[] args) {
    try {
      if(args.Length!=2)return 2;
      Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
      var doc=DwgReader.Read(args[0],Note);
      phase="write";
      DxfWriter.Write(args[1],doc,false,null,Note);
      Console.WriteLine(JsonSerializer.Serialize<object>(new {phase="done",version=doc.Header.Version.ToString(),entities=doc.Entities.Count},(JsonSerializerOptions)null));
      return 0;
    } catch(Exception e) {Console.Error.WriteLine(e.GetType().Name+": "+e.Message);return 1;}
  }
}
'''
(root/'Converter.cs').write_text(source,encoding='utf-8')
runtime=Path('C:/Program Files/dotnet/shared/Microsoft.NETCore.App/8.0.21')
refs=[p for p in runtime.glob('System.*.dll') if '.Native.' not in p.name]+[runtime/'mscorlib.dll',runtime/'netstandard.dll',root/'ACadSharp.dll']
args=['C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe','/noconfig','/nologo','/nostdlib+','/target:exe','/out:'+str(root/'Converter.dll')]+['/reference:'+str(p) for p in refs]+[str(root/'Converter.cs')]
r=subprocess.run(args,capture_output=True,text=True,encoding='gb18030',errors='replace')
(root/('compile-'+str(len(list(root.glob('compile*.log'))))+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr)
if r.returncode:raise SystemExit(r.returncode)
(root/'Converter.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net8.0','framework':{'name':'Microsoft.NETCore.App','version':'8.0.21'},'rollForward':'Disable','configProperties':{'System.Reflection.Metadata.MetadataUpdater.IsSupported':False}}}))
print('compiled')
