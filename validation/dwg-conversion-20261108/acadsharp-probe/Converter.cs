using System;
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
