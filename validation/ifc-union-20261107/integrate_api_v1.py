from pathlib import Path
def edit(name,a,b):
 p=Path(name);s=p.read_text(encoding='utf-8');assert s.count(a)==1,(name,a);p.write_text(s.replace(a,b),encoding='utf-8',newline='\n')
p=Path('backend/requirements.txt');p.write_text(p.read_text()+'manifold3d==3.5.4\n',newline='\n')
edit('backend/parser_runtime.py',"'cad':('ezdxf','ifcopenshell')","'cad':('ezdxf','ifcopenshell','manifold3d')")
edit('backend/parser_runtime.py',"'ifc_geometry.py','mesh_topology.py'","'ifc_geometry.py','mesh_topology.py','ifc_union.py'")
edit('backend/parser_runtime.py',"(kind!='drawing' or len(encoded)>1024)","(kind not in {'drawing','cad'} or len(encoded)>1024)")
edit('backend/parser_worker.py',"            result=parse(source);maximum=8*1024**2","""            if len(options)>1:raise ValueError('Unexpected CAD options')
            if options:
                from ifc_union import measure_union
                values=json.loads(options[0])
                if not isinstance(values,dict) or set(values)!={'operation','product_ids'} or values['operation']!='ifc_union':
                    raise ValueError('Invalid CAD operation')
                result=measure_union(source,values['product_ids'])
            else:
                result=parse(source)
            maximum=8*1024**2""")
edit('backend/cad.py',"'ifc_geometry':core.sha(Path(__file__).with_name('ifc_geometry.py')),","'ifc_geometry':core.sha(Path(__file__).with_name('ifc_geometry.py')),\n        'ifc_union':core.sha(Path(__file__).with_name('ifc_union.py')),")
p=Path('backend/extensions.py');s=p.read_text();pos=s.index('from .cad import');end=s.index('\n',pos)
s=s[:end]+"\nfrom .cad_union import IfcUnions, UnionRequest, union_report"+s[end:]
needle="    @app.post('/api/projects/{project_id}/thermal', status_code=201)"
assert s.count(needle)==1
routes="""    unions = IfcUnions(cad)

    @app.post('/api/projects/{project_id}/ifc-unions', status_code=201)
    def ifc_union_create(project_id: str, body: UnionRequest):
        return unions.create(project_id, body)

    @app.get('/api/projects/{project_id}/ifc-unions')
    def ifc_union_history(project_id: str):
        return [unions.view(project_id, row['union_id']) for row in domain.store.list('union', project_id)]

    @app.get('/api/projects/{project_id}/ifc-unions/{union_id}')
    def ifc_union_record(project_id: str, union_id: str):
        return unions.view(project_id, union_id)

    @app.get('/api/projects/{project_id}/ifc-unions/{union_id}/report.html', response_class=HTMLResponse)
    def ifc_union_html(project_id: str, union_id: str):
        return union_report(unions.view(project_id, union_id))

"""
s=s.replace(needle,routes+needle);p.write_text(s,encoding='utf-8',newline='\n')
