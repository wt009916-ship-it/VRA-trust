"""Re-extract only selected published numeric facts from the fixed public ZIP."""
import hashlib,io,json,sys,zipfile
from pathlib import Path
# xlrd is a verification-only dependency in an explicitly supplied directory.
sys.path.insert(0,sys.argv[3]);import xlrd
archive=Path(sys.argv[1]);output=Path(sys.argv[2]);assert not output.exists()
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='ec67e5f2f05a8b91447cd590022a118156f22ebf18a2919ae7e453ed76c0b909'
member='B-EX-Calibration-BaseCase-Utility-Data.xls'
with zipfile.ZipFile(io.BytesIO(archive.read_bytes())) as z:
    info=z.getinfo(member);assert info.file_size==46592;raw=z.read(member)
book=xlrd.open_workbook(file_contents=raw,on_demand=True);sheet=book.sheet_by_name('Utility Data-Cooling Cases');facts={'source_member':member,'sheets':{'Utility Data-Cooling Cases':[sheet.row_values(i) for i in range(18)]}}
output.write_text(json.dumps(facts,indent=2)+'\n',encoding='utf8');print(json.dumps({'workbook_sha256':hashlib.sha256(raw).hexdigest(),'reader_version':xlrd.__version__,'selected_cells':['D'+str(i) for i in range(7,19)],'facts_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'nature':'published synthetic utility data; not measured building'}))
book.release_resources()
